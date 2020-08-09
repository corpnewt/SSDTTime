import sys, os
from . import run

class Reveal:

    def __init__(self):
        self.r = run.Run()
        return
    
    def get_parent(self, path):
        return os.path.normpath(os.path.join(path, os.pardir))

    def reveal(self, path, new_window = False):
        # Reveals the passed path in Finder - only works on macOS
        if not sys.platform == "darwin":
            return ("", "macOS Only", 1)
        if not path:
            # No path sent - nothing to reveal
            return ("", "No path specified", 1)
        # Build our script - then convert it to a single line task
        if not os.path.exists(path):
            # Not real - bail
            return ("", "{} - doesn't exist".format(path), 1)
        # Get the absolute path
        path = os.path.abspath(path)
        command = ["osascript"]
        if new_window:
            command.extend([
                "-e", "set p to \"{}\"".format(path.replace("\"", "\\\"")),
                "-e", "tell application \"Finder\"",
                "-e", "reveal POSIX file p as text",
                "-e", "activate",
                "-e", "end tell"
            ])
        else:
            if path == self.get_parent(path):
                command.extend([
                    "-e", "set p to \"{}\"".format(path.replace("\"", "\\\"")),
                    "-e", "tell application \"Finder\"",
                    "-e", "reopen",
                    "-e", "activate",
                    "-e", "set target of window 1 to (POSIX file p as text)",
                    "-e", "end tell"
                ])
            else:
                command.extend([
                    "-e", "set o to \"{}\"".format(self.get_parent(path).replace("\"", "\\\"")),
                    "-e", "set p to \"{}\"".format(path.replace("\"", "\\\"")),
                    "-e", "tell application \"Finder\"",
                    "-e", "reopen",
                    "-e", "activate",
                    "-e", "set target of window 1 to (POSIX file o as text)",
                    "-e", "select (POSIX file p as text)",
                    "-e", "end tell"
                ])
        return self.r.run({"args" : command})

    def notify(self, title = None, subtitle = None, sound = None):
        # Sends a notification
        if not title:
            return ("", "Malformed dict", 1)
        # Build our notification
        n_text = "display notification with title \"{}\"".format(title.replace("\"", "\\\""))
        if subtitle:
            n_text += " subtitle \"{}\"".format(subtitle.replace("\"", "\\\""))
        if sound:
            n_text += " sound name \"{}\"".format(sound.replace("\"", "\\\""))
        command = ["osascript", "-e", n_text]
        return self.r.run({"args" : command})
