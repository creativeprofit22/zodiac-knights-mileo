// Decompile selected functions to one .c file per class.
// Args: <targets.tsv> <out_dir> [timeout_s] [threads]
// targets.tsv lines (written by the zk `ghidra` stage): rva_hex \t relative/path.c
//
// Resumable and streaming: each class file is written as soon as its functions are done
// (temp file + rename), and existing files are skipped on re-runs. Uses a fixed pool of
// worker threads, each with its own long-lived DecompInterface. (Ghidra's ParallelDecompiler
// kept every result in memory and leaked disposer threads on timeouts until the JVM could
// not create native threads, losing the whole export.)
// Scheduling is per function, files with the most functions first, so one big class is
// spread over all workers instead of running alone on one; the last function of a file
// joins its blocks in RVA order and writes the file. Progress is printed every 60 s.
// Ported from SSA (creativeprofit22/ssa@6e1be49).
// @category zk

import java.io.BufferedReader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class Il2CppExport extends GhidraScript {

    private static final int PROGRESS_SECONDS = 60;

    private final List<DecompInterface> all = Collections.synchronizedList(new ArrayList<>());
    private ThreadLocal<DecompInterface> local;

    private static final class FileJob {
        final String rel;
        final Function[] funcs;
        final String[] parts;
        final AtomicInteger remaining;

        FileJob(String rel, Map<Address, Function> byAddr) {
            this.rel = rel;
            this.funcs = byAddr.values().toArray(new Function[0]);
            this.parts = new String[funcs.length];
            this.remaining = new AtomicInteger(funcs.length);
        }
    }

    private DecompInterface newInterface() {
        DecompInterface ifc = new DecompInterface();
        ifc.setOptions(new DecompileOptions());
        ifc.toggleCCode(true);
        ifc.toggleSyntaxTree(false);
        ifc.setSimplificationStyle("decompile");
        if (!ifc.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler failed to open program: " + ifc.getLastMessage());
        }
        all.add(ifc);
        return ifc;
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Path targets = Path.of(args[0]);
        Path out = Path.of(args[1]);
        int timeout = args.length > 2 ? Integer.parseInt(args[2]) : 30;
        int threads = args.length > 3 ? Integer.parseInt(args[3])
            : Math.max(1, Runtime.getRuntime().availableProcessors() / 2);

        Address base = currentProgram.getImageBase();
        Map<String, Map<Address, Function>> byFile = new TreeMap<>();
        int missing = 0, total = 0;
        try (BufferedReader r = Files.newBufferedReader(targets, StandardCharsets.UTF_8)) {
            String line;
            while ((line = r.readLine()) != null) {
                String[] p = line.split("\t", -1);
                Address a = base.add(Long.parseLong(p[0], 16));
                Function f = getFunctionAt(a);
                if (f == null) { missing++; continue; }
                if (byFile.computeIfAbsent(p[1], k -> new TreeMap<>()).putIfAbsent(a, f) == null) total++;
            }
        }
        List<FileJob> todo = new ArrayList<>();
        int todoFuncs = 0;
        for (Map.Entry<String, Map<Address, Function>> e : byFile.entrySet()) {
            if (!Files.exists(out.resolve(e.getKey()))) {
                FileJob job = new FileJob(e.getKey(), e.getValue());
                todo.add(job);
                todoFuncs += job.funcs.length;
            }
        }
        // Largest files first so they spread across all workers; ties keep path order.
        todo.sort(Comparator.comparingInt((FileJob j) -> -j.funcs.length).thenComparing(j -> j.rel));
        println("Il2CppExport: decompiling " + total + " functions (" + missing + " not found) in "
            + byFile.size() + " files; " + todo.size() + " files to do, " + threads + " threads, timeout "
            + timeout + "s");

        local = ThreadLocal.withInitial(this::newInterface);
        AtomicInteger doneFiles = new AtomicInteger(), doneFuncs = new AtomicInteger(), failed = new AtomicInteger();
        final int nFiles = todo.size(), nFuncs = todoFuncs;
        final long start = System.nanoTime();
        ScheduledExecutorService ticker = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "Il2CppExport-progress");
            t.setDaemon(true);
            return t;
        });
        ticker.scheduleAtFixedRate(() -> println("Il2CppExport: progress "
            + TimeUnit.NANOSECONDS.toSeconds(System.nanoTime() - start) + "s: files " + doneFiles.get() + "/"
            + nFiles + ", functions " + doneFuncs.get() + "/" + nFuncs + ", failed " + failed.get()),
            PROGRESS_SECONDS, PROGRESS_SECONDS, TimeUnit.SECONDS);
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        List<Future<?>> futures = new ArrayList<>();
        try {
            for (FileJob job : todo) {
                for (int i = 0; i < job.funcs.length; i++) {
                    final int idx = i;
                    futures.add(pool.submit(() -> {
                        if (monitor.isCancelled()) return null;
                        Function f = job.funcs[idx];
                        DecompileResults res = local.get().decompileFunction(f, timeout, monitor);
                        StringBuilder sb = new StringBuilder();
                        sb.append("// ").append(f.getName()).append(" @ ").append(f.getEntryPoint()).append('\n');
                        if (res != null && res.decompileCompleted() && res.getDecompiledFunction() != null) {
                            sb.append(res.getDecompiledFunction().getC());
                        } else {
                            failed.incrementAndGet();
                            sb.append("// decompilation failed: ")
                              .append(res == null ? "no result" : res.getErrorMessage()).append('\n');
                        }
                        sb.append('\n');
                        job.parts[idx] = sb.toString();
                        doneFuncs.incrementAndGet();
                        // decrementAndGet publishes every parts[] write to the thread that sees 0
                        if (job.remaining.decrementAndGet() == 0) {
                            Path p = out.resolve(job.rel);
                            Files.createDirectories(p.getParent());
                            Path tmp = p.resolveSibling(p.getFileName() + ".part");
                            try (Writer w = Files.newBufferedWriter(tmp, StandardCharsets.UTF_8)) {
                                for (String part : job.parts) w.write(part);
                            }
                            Files.move(tmp, p, StandardCopyOption.REPLACE_EXISTING);
                            doneFiles.incrementAndGet();
                        }
                        return null;
                    }));
                }
            }
            pool.shutdown();
            for (Future<?> fu : futures) {
                fu.get();
            }
        } finally {
            pool.shutdownNow();
            ticker.shutdownNow();
            synchronized (all) {
                for (DecompInterface ifc : all) ifc.dispose();
            }
        }
        println("Il2CppExport: files=" + doneFiles.get() + " functions=" + doneFuncs.get()
            + " failed=" + failed.get());
    }
}
