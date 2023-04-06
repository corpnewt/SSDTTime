import os, tempfile, shutil, plistlib, sys, binascii, zipfile, getpass
from . import run, downloader, utils

class DSDT:
    def __init__(self, **kwargs):
        self.dl = downloader.Downloader()
        self.r  = run.Run()
        self.u    = utils.Utils("SSDT Time")
        self.iasl_url_macOS = "https://raw.githubusercontent.com/acidanthera/MaciASL/master/Dist/iasl-stable"
        self.iasl_url_linux = "https://raw.githubusercontent.com/corpnewt/linux_iasl/main/iasl.zip"
        self.iasl_url_windows = "https://acpica.org/sites/acpica/files/iasl-win-20200528.zip"
        self.acpi_binary_tools = "https://www.acpica.org/downloads/binary-tools"
        self.iasl = self.check_iasl()
        if not self.iasl:
            raise Exception("Could not locate or download iasl!")
        self.dsdt       = None
        self.dsdt_raw   = None
        self.dsdt_lines = None
        self.dsdt_scope = []
        self.dsdt_paths = []

    def load(self, dsdt): # Requires the full path
        cwd = os.getcwd()
        got_origin = False
        origin_path = dsdt
        ret = True
        if os.path.isdir(dsdt):
            # Check for DSDT.aml inside
            if os.path.exists(os.path.join(dsdt,"DSDT.aml")):
                origin_path = dsdt
                got_origin = True
                dsdt = os.path.join(dsdt,"DSDT.aml")
            else:
                print("No DSDT.aml in folder.")
                return False
        #elif os.path.basename(dsdt).lower() != "dsdt.aml":
        #    print("Name is not DSDT.aml.")
        #    return False
        temp = tempfile.mkdtemp()
        try:
            if got_origin:
                got_origin = False # Reset until we get an SSDT file copied
                for x in os.listdir(origin_path):
                    if x.startswith(".") or x.lower().startswith("ssdt-x") or not x.lower().endswith(".aml"):
                        # Not needed - skip
                        continue
                    if x.lower().startswith("ssdt"):
                        got_origin = True # Got at least one - nice
                    shutil.copy(os.path.join(origin_path,x),temp)
                dsdt_path = os.path.join(temp,"DSDT.aml")
            else:
                shutil.copy(dsdt,temp)
                dsdt_path = os.path.join(temp,os.path.basename(dsdt))
            dsdt_l_path = os.path.splitext(dsdt_path)[0]+".dsl"
            os.chdir(temp)
            if got_origin:
                # Have at least one SSDT to use while decompiling
                if sys.platform == "win32":
                    out = self.r.run({"args":"{} -dl -l DSDT.aml SSDT*".format(self.iasl),"shell":True})
                else:
                    out = self.r.run({"args":"{} -da -dl -l DSDT.aml SSDT*".format(self.iasl),"shell":True})
            else:
                # Just the DSDT - might be incomplete though
                if sys.platform == "win32":
                    out = self.r.run({"args":[self.iasl,"-dl","-l",dsdt_path]})
                else:
                    out = self.r.run({"args":[self.iasl,"-da","-dl","-l",dsdt_path]})
            if out[2] != 0 or not os.path.exists(dsdt_l_path):
                raise Exception("Failed to decompile {}".format(os.path.basename(dsdt_path)))
            with open(dsdt_l_path,"r") as f:
                self.dsdt = f.read()
                self.dsdt_lines = self.dsdt.split("\n")
                self.get_scopes()
                self.dsdt_paths = self.get_paths()
            with open(dsdt_path,"rb") as f:
                self.dsdt_raw = f.read()
        except Exception as e:
            print(e)
            ret = False
        os.chdir(cwd)
        shutil.rmtree(temp,ignore_errors=True)
        return ret

    def get_latest_iasl(self):
        # Helper to scrape https://www.acpica.org/downloads/binary-tools for the latest
        # iasl zip
        try:
            source = self.dl.get_string(self.acpi_binary_tools)
            # acpica.org seems to muck up their links from time to time - let's try to get the first
            # windows attachment that *isn't* the hyperlink in the landing page.
            for line in source.split("\n"):
                if "/iasl-win-" in line and ".zip" in line and not '">iASL compiler and Windows ACPI tools' in line:
                    return line.split('<a href="')[1].split('"')[0]
        except: pass
        return None
    
    def check_iasl(self,try_downloading=True):
        if sys.platform == "win32":
            targets = (os.path.join(os.path.dirname(os.path.realpath(__file__)), "iasl.exe"),)
        else:
            targets = (
                os.path.join(os.path.dirname(os.path.realpath(__file__)), "iasl-dev"),
                os.path.join(os.path.dirname(os.path.realpath(__file__)), "iasl-stable"),
                os.path.join(os.path.dirname(os.path.realpath(__file__)), "iasl-legacy"),
                os.path.join(os.path.dirname(os.path.realpath(__file__)), "iasl")
            )
        target = next((t for t in targets if os.path.exists(t)),None)
        if target or not try_downloading:
            # Either found it - or we didn't, and have already tried downloading
            return target
        # Need to download
        temp = tempfile.mkdtemp()
        try:
            if sys.platform == "darwin":
                self._download_and_extract(temp,self.iasl_url_macOS)
            elif sys.platform.startswith("linux"):
                self._download_and_extract(temp,self.iasl_url_linux)
            elif sys.platform == "win32":
                iasl_url_windows = self.get_latest_iasl()
                if not iasl_url_windows: raise Exception("Could not get latest iasl for Windows")
                self._download_and_extract(temp,iasl_url_windows)
            else: 
                raise Exception("Unknown OS")
        except Exception as e:
            print("An error occurred :(\n - {}".format(e))
        shutil.rmtree(temp, ignore_errors=True)
        # Check again after downloading
        return self.check_iasl(try_downloading=False)

    def _download_and_extract(self, temp, url):
        ztemp = tempfile.mkdtemp(dir=temp)
        zfile = os.path.basename(url)
        print("Downloading {}".format(os.path.basename(url)))
        self.dl.stream_to_file(url, os.path.join(ztemp,zfile), False)
        search_dir = ztemp
        if zfile.lower().endswith(".zip"):
            print(" - Extracting")
            search_dir = tempfile.mkdtemp(dir=temp)
            # Extract with built-in tools \o/
            with zipfile.ZipFile(os.path.join(ztemp,zfile)) as z:
                z.extractall(search_dir)
        script_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)))
        for x in os.listdir(search_dir):
            if x.lower().startswith(("iasl","acpidump")):
                # Found one
                print(" - Found {}".format(x))
                if sys.platform != "win32":
                    print("   - Chmod +x")
                    self.r.run({"args":["chmod","+x",os.path.join(search_dir,x)]})
                print("   - Copying to {} directory".format(os.path.basename(script_dir)))
                shutil.copy(os.path.join(search_dir,x), os.path.join(script_dir,x))

    def dump_dsdt(self, output, decompile = True):
        self.u.head("Dumping DSDT")
        print("")
        res = self.check_output(output)
        if sys.platform.startswith("linux"):
            print("Checking if DSDT exists")
            e = "/sys/firmware/acpi/tables/DSDT"
            dsdt_path = os.path.join(res,"DSDT.aml")
            if os.path.isfile(e):
                print("Copying DSDT to safe location.")
                print("You have to enter your password to copy the file:")
                out = self.r.run({"args":["sudo", "cp", e, dsdt_path]})
                if out[2] != 0:
                    print(" - {}".format(out[1]))
                print("Changing file ownership")
                out = self.r.run({"args":["sudo", "chown", getpass.getuser(), dsdt_path]})
                if out[2] != 0:
                    print(" - {}".format(out[1]))
                print("Success!")
                if not decompile: # Not attempting to decompile it - just return the path
                    return dsdt_path
                if self.load(dsdt_path):
                    self.u.grab("Press [enter] to return to main menu...")
                    return dsdt_path
                else:
                    print("Loading file failed!")
                    self.u.grab("Press [enter] to return to main menu...")
                    return 
            else:
                print("Couldn't find DSDT table")
                self.u.grab("Press [enter] to return to main menu...")
                return 
        elif sys.platform == "win32":
            print("Dumping DSDT table")
            target = os.path.join(os.path.dirname(os.path.realpath(__file__)),"acpidump.exe")
            dump = os.path.join(res,"dsdt.dat")
            dsdt_path = os.path.join(res,"DSDT.aml")
            if os.path.exists(target):
                # Dump to the target folder
                cwd = os.getcwd()
                os.chdir(res)
                out = self.r.run({"args":[target, "-b", "-n", "dsdt"]})
                os.chdir(cwd)
                if out[2] != 0:
                    print(" - {}".format(out[1]))
                    return
                print("Dump successful!")
                print("Moving DSDT to better location.")
                shutil.move(dump,dsdt_path)
                if not decompile: # Not attempting to decompile it - just return the path
                    return dsdt_path
                if self.load(dsdt_path):
                    print("Success!")
                    self.u.grab("Press [enter] to return to main menu...")
                    return dsdt_path
                else:
                    print("Loading file failed!")
                    self.u.grab("Press [enter] to return to main menu...")
                    return 
            else:
                print("Failed to locate acpidump.exe")
                self.u.grab("Press [enter] to return to main menu...")
                return 
        else:
            print("Unsupported platform for DSDT dumping.")
            self.u.grab("Press [enter] to return to main menu...")
            return 

    def check_output(self, output):
        t_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), output)
        if not os.path.isdir(t_folder):
            os.mkdir(t_folder)
        return t_folder

    def get_hex_from_int(self, total, pad_to = 4):
        hex_str = hex(total)[2:].upper().rjust(pad_to,"0")
        return "".join([hex_str[i:i + 2] for i in range(0, len(hex_str), 2)][::-1])

    def get_hex(self, line):
        # strip the header and commented end
        return line.split(":")[1].split("//")[0].replace(" ","")

    def get_line(self, line):
        # Strip the header and commented end - no space replacing though
        line = line.split("//")[0]
        if ":" in line:
            return line.split(":")[1]
        return line

    def get_hex_bytes(self, line):
        return binascii.unhexlify(line)

    def find_previous_hex(self, index=0):
        # Returns the index of the previous set of hex digits before the passed index
        start_index = -1
        end_index   = -1
        old_hex = True
        for i,line in enumerate(self.dsdt_lines[index::-1]):
            if old_hex:
                if not self.is_hex(line):
                    # Broke out of the old hex
                    old_hex = False
                continue
            # Not old_hex territory - check if we got new hex
            if self.is_hex(line): # Checks for a :, but not in comments
                end_index = index-i
                hex_text,start_index = self.get_hex_ending_at(end_index)
                return (hex_text, start_index, end_index)
        return ("",start_index,end_index)
    
    def find_next_hex(self, index=0):
        # Returns the index of the next set of hex digits after the passed index
        start_index = -1
        end_index   = -1
        old_hex = True
        for i,line in enumerate(self.dsdt_lines[index:]):
            if old_hex:
                if not self.is_hex(line):
                    # Broke out of the old hex
                    old_hex = False
                continue
            # Not old_hex territory - check if we got new hex
            if self.is_hex(line): # Checks for a :, but not in comments
                start_index = i+index
                hex_text,end_index = self.get_hex_starting_at(start_index)
                return (hex_text, start_index, end_index)
        return ("",start_index,end_index)

    def is_hex(self, line):
        return ":" in line.split("//")[0]

    def get_hex_starting_at(self, start_index):
        # Returns a tuple of the hex, and the ending index
        hex_text = ""
        index = -1
        for i,x in enumerate(self.dsdt_lines[start_index:]):
            if not self.is_hex(x):
                break
            hex_text += self.get_hex(x)
            index = i+start_index
        return (hex_text, index)

    def get_hex_ending_at(self, start_index):
        # Returns a tuple of the hex, and the ending index
        hex_text = ""
        index = -1
        for i,x in enumerate(self.dsdt_lines[start_index::-1]):
            if not self.is_hex(x):
                break
            hex_text = self.get_hex(x)+hex_text
            index = start_index-i
        return (hex_text, index)

    def get_shortest_unique_pad(self, current_hex, index, instance=0):
        try:    left_pad  = self.get_unique_pad(current_hex, index, False, instance)
        except: left_pad  = None
        try:    right_pad = self.get_unique_pad(current_hex, index, True, instance)
        except: right_pad = None
        try:    mid_pad   = self.get_unique_pad(current_hex, index, None, instance)
        except: mid_pad   = None
        if left_pad == right_pad == mid_pad == None: raise Exception("No unique pad found!")
        # We got at least one unique pad
        min_pad = None
        for x in (left_pad,right_pad,mid_pad):
            if x == None: continue # Skip
            if min_pad == None or len(x[0]+x[1]) < len(min_pad[0]+min_pad[1]):
                min_pad = x
        return min_pad

    def get_unique_pad(self, current_hex, index, direction=None, instance=0):
        # Returns any pad needed to make the passed patch unique
        # direction can be True = forward, False = backward, None = both
        start_index = index
        line,last_index = self.get_hex_starting_at(index)
        if not current_hex in line:
            raise Exception("{} not found in DSDT at index {}-{}!".format(current_hex,start_index,last_index))
        padl = padr = ""
        parts = line.split(current_hex)
        if instance >= len(parts)-1:
            raise Exception("Instance out of range!")
        linel = current_hex.join(parts[0:instance+1])
        liner = current_hex.join(parts[instance+1:])
        last_check = True # Default to forward
        while True:
            # Check if our hex string is unique
            check_bytes = self.get_hex_bytes(padl+current_hex+padr)
            if self.dsdt_raw.count(check_bytes) == 1: # Got it!
                break
            if direction == True or (direction == None and len(padr)<=len(padl)):
                # Let's check a forward byte
                if not len(liner):
                    # Need to grab more
                    liner, _index, last_index = self.find_next_hex(last_index)
                    if last_index == -1: raise Exception("Hit end of file before unique hex was found!")
                padr  = padr+liner[0:2]
                liner = liner[2:]
                continue
            if direction == False or (direction == None and len(padl)<=len(padr)):
                # Let's check a backward byte
                if not len(linel):
                    # Need to grab more
                    linel, start_index, _index = self.find_previous_hex(start_index)
                    if _index == -1: raise Exception("Hit end of file before unique hex was found!")
                padl  = linel[-2:]+padl
                linel = linel[:-2]
                continue
            break
        return (padl,padr)
    
    def get_devices(self,search=None,types=("Device (","Scope ("),strip_comments=False):
        # Returns a list of tuples organized as (Device/Scope,d_s_index,matched_index)
        if search == None:
            return []
        last_device = None
        device_index = 0
        devices = []
        for index,line in enumerate(self.dsdt_lines):
            if self.is_hex(line):
                continue
            line = self.get_line(line) if strip_comments else line
            if any ((x for x in types if x in line)):
                # Got a last_device match
                last_device = line
                device_index = index
            if search in line:
                # Got a search hit - add it
                devices.append((last_device,device_index,index))
        return devices

    def get_scope(self,starting_index=0,add_hex=False,strip_comments=False):
        # Walks the scope starting at starting_index, and returns when
        # we've exited
        brackets = None
        scope = []
        for line in self.dsdt_lines[starting_index:]:
            if self.is_hex(line):
                if add_hex:
                    scope.append(line)
                continue
            line = self.get_line(line) if strip_comments else line
            scope.append(line)
            if brackets == None:
                if line.count("{"):
                    brackets = line.count("{")
                continue
            brackets = brackets + line.count("{") - line.count("}")
            if brackets <= 0:
                # We've exited the scope
                return scope
        return scope

    def get_scopes(self):
        self.dsdt_scope = []
        for index,line in enumerate(self.dsdt_lines):
            if self.is_hex(line): continue
            if any(x in line for x in ("Processor (","Scope (","Device (","Method (","Name (")):
                self.dsdt_scope.append((line,index))
        return self.dsdt_scope

    def get_paths(self):
        if not self.dsdt_scope: self.get_scopes()
        starting_indexes = []
        for index,scope in enumerate(self.dsdt_scope):
            if not scope[0].strip().startswith(("Processor (","Device (","Method (","Name (")): continue
            # Got a device - add its index
            starting_indexes.append(index)
        if not len(starting_indexes): return None
        paths = []
        for x in starting_indexes:
            paths.append(self.get_path_starting_at(x))
        return sorted(paths)

    def get_path_of_type(self, obj_type="Device", obj="HPET"):
        paths = []
        for path in self.dsdt_paths:
            if path[2].lower() == obj_type.lower() and path[0].upper().endswith(obj.upper()):
                paths.append(path)
        return sorted(paths)

    def get_device_paths(self, obj="HPET"):
        return self.get_path_of_type(obj_type="Device",obj=obj)

    def get_method_paths(self, obj="_STA"):
        return self.get_path_of_type(obj_type="Method",obj=obj)

    def get_name_paths(self, obj="CPU0"):
        return self.get_path_of_type(obj_type="Name",obj=obj)

    def get_processor_paths(self, obj="Processor"):
        return self.get_path_of_type(obj_type="Processor",obj=obj)

    def get_device_paths_with_hid(self, hid="ACPI000E"):
        if not self.dsdt_scope: self.get_scopes()
        starting_indexes = []
        for index,line in enumerate(self.dsdt_lines):
            if self.is_hex(line): continue
            if hid.upper() in line.upper():
                starting_indexes.append(index)
        if not starting_indexes: return starting_indexes
        devices = []
        for i in starting_indexes:
            # Walk backwards and get the next parent device
            pad = len(self.dsdt_lines[i]) - len(self.dsdt_lines[i].lstrip(" "))
            for sub,line in enumerate(self.dsdt_lines[i::-1]):
                if "Device (" in line and len(line)-len(line.lstrip(" ")) < pad:
                    # Add it if it's already in our dsdt_paths - if not, add the current line
                    device = next((x for x in self.dsdt_paths if x[1]==i-sub),None)
                    if device: devices.append(device)
                    else: devices.append((line,i-sub))
                    break
        return devices

    def _normalize_types(self, line):
        # Replaces Name, Processor, Device, and Method with Scope for splitting purposes
        return line.replace("Name","Scope").replace("Processor","Scope").replace("Device","Scope").replace("Method","Scope")

    def get_path_starting_at(self, starting_index=0):
        if not self.dsdt_scope: self.get_scopes()
        # Walk the scope backwards, keeping track of changes
        pad = None
        path = []
        obj_type = next((x for x in ("Processor","Method","Scope","Device","Name") if x+" (" in self.dsdt_scope[starting_index][0]),"Unknown Type")
        for scope,original_index in self.dsdt_scope[starting_index::-1]:
            new_pad = self._normalize_types(scope).split("Scope (")[0]
            if pad == None or new_pad < pad:
                pad = new_pad
                obj = self._normalize_types(scope).split("Scope (")[1].split(")")[0].split(",")[0]
                path.append(obj)
                if obj in ("_SB","_SB_","_PR","_PR_") or obj.startswith(("\\","_SB.","_SB_.","_PR.","_PR_.")): break # This is a full scope
        path = path[::-1]
        if len(path) and path[0] == "\\": path.pop(0)
        if any(("^" in x for x in path)): # Accommodate caret notation
            new_path = []
            for x in path:
                if x.count("^"):
                    # Remove the last Y paths to account for going up a level
                    del new_path[-1*x.count("^"):]
                new_path.append(x.replace("^","")) # Add the original, removing any ^ chars
            path = new_path
        path = ".".join(path)
        path = "\\"+path if path[0] != "\\" else path
        return (path, self.dsdt_scope[starting_index][1], obj_type)
