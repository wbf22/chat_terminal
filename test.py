import pty, os, subprocess, select



class TalkProcess:

    _master = 0
    _process = None


    def __init__(self, command) -> tuple[int, subprocess.Popen]:
        # kill last process if running
        if not self.is_finished():
            self.kill()
        
        # set up file descriptors and start process
        self._master, slave = pty.openpty()
        self._process = subprocess.Popen(
            command,
            shell=True,
            stdin=slave,
            stdout=slave,
            stderr=slave
        )

    def get_output(self) -> str:
        output = []
        while True:
            if select.select([self._master], [], [], 1)[0]:
                try:
                    chunk = os.read(self._master, 1024).decode()
                    output.append(chunk)
                except OSError:
                    break  # process has ended
            else:
                break  # no output, waiting for input

        return "".join(output)

    def send_input(self, user_input: str):
        os.write(self._master, (user_input + "\n").encode())

    def kill(self):
        if self._process != None:
            self._process.kill()

    def is_finished(self):
        return self._process != None and self._process.poll() != None


process = TalkProcess('echo "hi"')
print(process.get_output(), end="")
print(process.is_finished())
print(process.get_output(), end="")


