import java.lang.instrument.Instrumentation;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.BufferedWriter;

public class BlockStateDump {
    public static void agentmain(String output, Instrumentation instrumentation) throws Exception {
        Class<?> blockClass = null;
        for (Class<?> type : instrumentation.getAllLoadedClasses()) {
            if (type.getName().equals("net.minecraft.class_2248")) blockClass = type;
        }
        if (blockClass == null) throw new IllegalStateException("Block registry not initialized");
        Field registryField = blockClass.getDeclaredField("field_10651");
        registryField.setAccessible(true);
        Object states = registryField.get(null);
        Method rawId = null;
        for (Method method : blockClass.getDeclaredMethods()) {
            if (method.getName().equals("method_9507")) rawId = method;
        }
        if (rawId == null) throw new IllegalStateException("Block ID getter missing");
        rawId.setAccessible(true);
        try (BufferedWriter writer = Files.newBufferedWriter(Path.of(output))) {
            for (Object state : (Iterable<?>) states) {
                writer.write(rawId.invoke(null, state) + "\t" + state + "\n");
            }
        }
    }
}
