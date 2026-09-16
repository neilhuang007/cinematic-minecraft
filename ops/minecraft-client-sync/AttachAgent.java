import com.sun.tools.attach.VirtualMachine;

public class AttachAgent {
    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            throw new IllegalArgumentException("Usage: AttachAgent <pid> <agent-jar> [agent-args]");
        }
        VirtualMachine vm = VirtualMachine.attach(args[0]);
        try {
            vm.loadAgent(args[1], args.length >= 3 ? args[2] : "");
        } finally {
            vm.detach();
        }
    }
}
