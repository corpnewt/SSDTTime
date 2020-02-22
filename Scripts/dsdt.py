#!/usr/bin/env python
# 0.0.0
import os, tempfile, shutil, plistlib, sys, binascii, zipfile, getpass
sys.path.append(os.path.abspath(os.path.dirname(os.path.realpath(__file__))))
import run, downloader, utils

class DSDT:
    def __init__(self, **kwargs):
        self.dl = downloader.Downloader()
        self.r  = run.Run()
        self.u    = utils.Utils("SSDT Time")
        self.iasl_url_macOS = "https://bitbucket.org/RehabMan/acpica/downloads/iasl.zip"
        self.iasl_url_linux = "http://amdosx.kellynet.nl/iasl.zip"
        self.iasl_url_windows = "https://acpica.org/sites/acpica/files/iasl-win-20180105.zip"
        self.iasl = self.check_iasl()
        if not self.iasl:
            raise Exception("Could not locate or download iasl!")
        self.dsdt       = None
        self.dsdt_raw   = None
        self.dsdt_lines = None

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
        elif os.path.basename(dsdt).lower() != "dsdt.aml":
            print("Name is not DSDT.aml.")
            return False
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
            with open(dsdt_path,"rb") as f:
                self.dsdt_raw = f.read()
        except Exception as e:
            print(e)
            ret = False
        os.chdir(cwd)
        shutil.rmtree(temp,ignore_errors=True)
        return ret
    
    def check_iasl(self):
        if sys.platform == "win32":
            target = os.path.join(os.path.dirname(os.path.realpath(__file__)), "iasl.exe")
        else:
            target = os.path.join(os.path.dirname(os.path.realpath(__file__)), "iasl")
        if not os.path.exists(target):
            # Need to download
            temp = tempfile.mkdtemp()
            try:
                if sys.platform == "darwin":
                    self._download_and_extract(temp,self.iasl_url_macOS)
                elif sys.platform == "linux":
                    self._download_and_extract(temp,self.iasl_url_linux)
                elif sys.platform == "win32":
                    self._download_and_extract(temp,self.iasl_url_windows)
                else: 
                    raise Exception  
            except Exception as e:
                print("An error occurred :(\n - {}".format(e))
            shutil.rmtree(temp, ignore_errors=True)
        if os.path.exists(target):
            return target
        return None

    def _download_and_extract(self, temp, url):
        ztemp = tempfile.mkdtemp(dir=temp)
        zfile = os.path.basename(url)
        print("Downloading {}".format(os.path.basename(url)))
        self.dl.stream_to_file(url, os.path.join(ztemp,zfile), False)
        print(" - Extracting")
        btemp = tempfile.mkdtemp(dir=temp)
        # Extract with built-in tools \o/
        with zipfile.ZipFile(os.path.join(ztemp,zfile)) as z:
            z.extractall(os.path.join(temp,btemp))
        script_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)))
        for x in os.listdir(os.path.join(temp,btemp)):
            if "iasl" in x.lower():
                # Found one
                print(" - Found {}".format(x))
                if sys.platform != "win32":
                    print("   - Chmod +x")
                    self.r.run({"args":["chmod","+x",os.path.join(btemp,x)]})
                print("   - Copying to {} directory".format(os.path.basename(script_dir)))
                shutil.copy(os.path.join(btemp,x), os.path.join(script_dir,x))
            if "acpidump" in x.lower():
                if sys.platform == "win32":
                    # Found one
                    print(" - Found {}".format(x))
                    print("   - Copying to {} directory".format(os.path.basename(script_dir)))
                    shutil.copy(os.path.join(btemp,x), os.path.join(script_dir,x))

    def dump_dsdt(self, output):
        self.u.head("Dumping DSDT")
        print("")
        res = self.check_output(output)
        if sys.platform == "linux":
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

    def get_unique_pad(self, current_hex, index, forward=True):
        # Returns any pad needed to make the passed patch unique
        start_index = index
        line,last_index = self.get_hex_starting_at(index)
        if not current_hex in line:
            raise Exception("{} not found in DSDT at index {}-{}!".format(current_hex,start_index,last_index))
        pad = ""
        line = current_hex.join(line.split(current_hex)[1:]) if forward else current_hex.join(line.split(current_hex)[:-1])
        while True:
            # Check if our hex string is unique
            check_bytes = self.get_hex_bytes(current_hex+pad) if forward else self.get_hex_bytes(pad+current_hex)
            if self.dsdt_raw.count(check_bytes) > 1:
                # More than one instance - add more pad
                if not len(line):
                    # Need to grab more 
                    line, start_index, last_index = self.find_next_hex(last_index) if forward else self.find_previous_hex(start_index)
                    if last_index == -1:
                        raise Exception("Hit end of file before unique hex was found!")
                pad  = pad+line[0:2] if forward else line[-2:]+pad
                line = line[2:] if forward else line[:-2]
                continue
            break
        return pad
    
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
