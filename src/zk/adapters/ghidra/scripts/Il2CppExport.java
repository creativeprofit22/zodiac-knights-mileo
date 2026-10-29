// Decompile selected functions to one .c file per class.
// Args: <targets.tsv> <out_dir> [timeout_s] [threads]
// targets.tsv lines (written by the zk `ghidra` stage): rva_hex \t relative/path.c
//
// Resumable and streaming: each class file is written as soon as its functions are done
// (temp file + rename), and existing files are skipped on re-runs. Uses a fixed pool of
// worker threads, each with its own long-lived DecompInterface. (Ghidra's ParallelDecompiler
// kept every result in memory and leaked disposer threads on timeouts until the JVM could
// not create native threads, losing the whole export.)
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
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class Il2CppExport extends GhidraScript {

    private final List<DecompInterface> all = Collections.synchronizedList(new ArrayList<>());
    private ThreadLocal<DecompInterface> local;

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
        List<String> todo = new ArrayList<>();
        for (String rel : byFile.keySet()) {
            if (!Files.exists(out.resolve(rel))) todo.add(rel);
        }
        println("Il2CppExport: decompiling " + total + " functions (" + missing + " not found) in "
            + byFile.size() + " files; " + todo.size() + " files to do, " + threads + " threads, timeout "
            + timeout + "s");

        local = ThreadLocal.withInitial(this::newInterface);
        AtomicInteger doneFiles = new AtomicInteger(), doneFuncs = new AtomicInteger(), failed = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        List<Future<?>> futures = new ArrayList<>();
        for (String rel : todo) {
            futures.add(pool.submit(() -> {
                if (monitor.isCancelled()) return null;
                DecompInterface ifc = local.get();
                StringBuilder sb = new StringBuilder();
                for (Function f : byFile.get(rel).values()) {
                    DecompileResults res = ifc.decompileFunction(f, timeout, monitor);
                    sb.append("// ").append(f.getName()).append(" @ ").append(f.getEntryPoint()).append('\n');
                    if (res != null && res.decompileCompleted() && res.getDecompiledFunction() != null) {
                        sb.append(res.getDecompiledFunction().getC());
                    } else {
                        failed.incrementAndGet();
                        sb.append("// decompilation failed: ")
                          .append(res == null ? "no result" : res.getErrorMessage()).append('\n');
                    }
                    sb.append('\n');
                    doneFuncs.incrementAndGet();
                }
                Path p = out.resolve(rel);
                Files.createDirectories(p.getParent());
                Path tmp = p.resolveSibling(p.getFileName() + ".part");
                try (Writer w = Files.newBufferedWriter(tmp, StandardCharsets.UTF_8)) {
                    w.write(sb.toString());
                }
                Files.move(tmp, p, StandardCopyOption.REPLACE_EXISTING);
                int n = doneFiles.incrementAndGet();
                if (n % 100 == 0) {
                    println("Il2CppExport: " + n + "/" + todo.size() + " files, " + doneFuncs.get()
                        + " functions, " + failed.get() + " failed");
                }
                return null;
            }));
        }
        pool.shutdown();
        try {
            for (Future<?> fu : futures) {
                fu.get();
            }
        } finally {
            pool.shutdownNow();
            synchronized (all) {
                for (DecompInterface ifc : all) ifc.dispose();
            }
        }
        println("Il2CppExport: files=" + doneFiles.get() + " functions=" + doneFuncs.get()
            + " failed=" + failed.get());
    }
}
