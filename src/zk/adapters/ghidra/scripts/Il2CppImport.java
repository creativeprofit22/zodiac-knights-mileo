// Apply Il2CppDumper output to the current program (Java port of the dumper's
// ghidra_with_struct.py, so no PyGhidra/Jython is needed).
// Args: <symbols.tsv> <il2cpp_ghidra.h | -> [disable-slow-analyzers: true|false]
// symbols.tsv lines (written by the zk ghidra adapter): kind \t rva_hex \t name \t signature
//   A = function start (Addresses), F = method (ScriptMethod), S = string literal,
//   M = metadata (ScriptMetadata), N = metadata method (ScriptMetadataMethod)
// Ported from SSA (creativeprofit22/ssa@6e1be49); a header that fails to parse fails the run.
// @category zk

import java.io.BufferedReader;
import java.io.FileInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import ghidra.app.cmd.function.ApplyFunctionSignatureCmd;
import ghidra.app.script.GhidraScript;
import ghidra.app.services.DataTypeManagerService;
import ghidra.app.util.cparser.C.CParser;
import ghidra.app.util.cparser.C.CParserUtils;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.DataType;
import ghidra.program.model.data.DataTypeManager;
import ghidra.program.model.data.FunctionDefinitionDataType;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;

public class Il2CppImport extends GhidraScript {

    static final String[] SLOW_ANALYZERS = {
        "Aggressive Instruction Finder", "Decompiler Parameter ID", "Function ID",
        "Embedded Media", "DWARF", "Condense Filler Bytes", "Create Address Tables",
        "Non-Returning Functions - Discovered", "Variadic Function Signature Override",
        // Both decompile every function (100k+ here): hours on this machine, and IL2CPP
        // signatures from script.json already give calling conventions and switch-free stubs.
        "Call Convention ID", "Decompiler Switch Analysis",
    };

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Path symbols = Path.of(args[0]);
        String header = args.length > 1 ? args[1] : "-";
        boolean fast = args.length > 2 && Boolean.parseBoolean(args[2]);

        if (fast) {
            for (String a : SLOW_ANALYZERS) {
                try {
                    setAnalysisOption(currentProgram, a, "false");
                } catch (Exception e) {
                    println("analyzer option not found: " + a);
                }
            }
        }

        DataTypeManager dtm = currentProgram.getDataTypeManager();
        if (!header.equals("-")) {
            long t = System.currentTimeMillis();
            CParser parser = new CParser(dtm, true, null);
            parser.setMonitor(monitor);
            try (FileInputStream in = new FileInputStream(header)) {
                parser.parse(in);
            }
            // a silent partial parse would leave most types undefined: surface it as a script error
            if (!parser.didParseSucceed()) {
                println(parser.getParseMessages());
                throw new IllegalStateException("il2cpp.h did not parse: " + parser.getParseMessages());
            }
            println("types parsed from " + header + " in " + (System.currentTimeMillis() - t) / 1000 + "s");
        }

        Address base = currentProgram.getImageBase();
        int named = 0, sigs = 0, failed = 0;
        try (BufferedReader r = Files.newBufferedReader(symbols, StandardCharsets.UTF_8)) {
            String line;
            while ((line = r.readLine()) != null) {
                monitor.checkCancelled();
                String[] p = line.split("\t", -1);
                Address addr = base.add(Long.parseLong(p[1], 16));
                String name = p[2].replace(' ', '-');
                String sig = p.length > 3 ? p[3] : "";
                try {
                    switch (p[0]) {
                        case "A" -> {
                            if (getFunctionAt(addr) == null) createFunction(addr, null);
                        }
                        case "F" -> {
                            Function f = getFunctionAt(addr);
                            if (f == null) f = createFunction(addr, name);
                            if (f == null) { failed++; break; }
                            f.setName(name, SourceType.USER_DEFINED);
                            named++;
                            if (!sig.isEmpty()) {
                                FunctionDefinitionDataType def = CParserUtils.parseSignature(
                                    (DataTypeManagerService) null, currentProgram, sig, false);
                                if (def != null) {
                                    new ApplyFunctionSignatureCmd(addr, def, SourceType.USER_DEFINED)
                                        .applyTo(currentProgram, monitor);
                                    sigs++;
                                }
                            }
                        }
                        case "S", "M", "N" -> {
                            createLabel(addr, name, true, SourceType.USER_DEFINED);
                            setEOLComment(addr, p[0].equals("S") ? sig : name);
                            if (p[0].equals("M") && !sig.isEmpty()) applyDataType(addr, sig);
                        }
                        default -> { }
                    }
                } catch (Exception e) {
                    failed++;
                }
            }
        }
        println("Il2CppImport: methods named=" + named + " signatures=" + sigs + " failed=" + failed);
    }

    private void applyDataType(Address addr, String type) throws Exception {
        String t = type.replace("*", " *").replace("  ", " ").strip();
        boolean ptr = t.endsWith(" *");
        String baseName = ptr ? t.substring(0, t.length() - 2).strip() : t;
        DataType[] found = getDataTypes(baseName);
        if (found.length != 1) return;
        DataType dt = ptr ? currentProgram.getDataTypeManager().getPointer(found[0]) : found[0];
        clearListing(addr, addr.add(dt.getLength() - 1));
        createData(addr, dt);
    }
}
