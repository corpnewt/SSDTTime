from Scripts import *
import getpass, os, tempfile, shutil, plistlib, sys, binascii, zipfile, re, string

class SSDT:
    def __init__(self, **kwargs):
        self.dl   = downloader.Downloader()
        self.u    = utils.Utils("SSDT Time")
        self.r    = run.Run()
        self.re   = reveal.Reveal()
        try:
            self.d = dsdt.DSDT()
        except Exception as e:
            print("Something went wrong :( - Aborting!\n - {}".format(e))
            exit(1)
        self.w = 80
        self.h = 24
        if os.name == "nt":
            os.system("color") # Allow ASNI color escapes.
            self.w = 120
            self.h = 30
        self.iasl = None
        self.dsdt = None
        self.scripts = "Scripts"
        self.output = "Results"
        self.legacy_irq = ["TMR","TIMR","IPIC","RTC"] # Could add HPET for extra patch-ness, but shouldn't be needed
        self.target_irqs = [0,2,8,11]
        self.illegal_names = ("XHC1","EHC1","EHC2","PXSX")
        # _OSI Strings found here: https://learn.microsoft.com/en-us/windows-hardware/drivers/acpi/winacpi-osi
        self.osi_strings = {
            "Windows 2000": "Windows 2000",
            "Windows XP": "Windows 2001",
            "Windows XP SP1": "Windows 2001 SP1",
            "Windows Server 2003": "Windows 2001.1",
            "Windows XP SP2": "Windows 2001 SP2",
            "Windows Server 2003 SP1": "Windows 2001.1 SP1",
            "Windows Vista": "Windows 2006",
            "Windows Vista SP1": "Windows 2006 SP1",
            "Windows Server 2008": "Windows 2006.1",
            "Windows 7, Win Server 2008 R2": "Windows 2009",
            "Windows 8, Win Server 2012": "Windows 2012",
            "Windows 8.1": "Windows 2013",
            "Windows 10": "Windows 2015",
            "Windows 10, version 1607": "Windows 2016",
            "Windows 10, version 1703": "Windows 2017",
            "Windows 10, version 1709": "Windows 2017.2",
            "Windows 10, version 1803": "Windows 2018",
            "Windows 10, version 1809": "Windows 2018.2",
            "Windows 10, version 1903": "Windows 2019",
            "Windows 10, version 2004": "Windows 2020",
            "Windows 11": "Windows 2021",
            "Windows 11, version 22H2": "Windows 2022"
        }
        self.pre_patches = (
            {
                "PrePatch":"GPP7 duplicate _PRW methods",
                "Comment" :"GPP7._PRW to XPRW to fix Gigabyte's Mistake",
                "Find"    :"3708584847500A021406535245470214065350525701085F505257",
                "Replace" :"3708584847500A0214065352454702140653505257010858505257"
            },
            {
                "PrePatch":"GPP7 duplicate UP00 devices",
                "Comment" :"GPP7.UP00 to UPXX to fix Gigabyte's Mistake",
                "Find"    :"1047052F035F53425F50434930475050375B82450455503030",
                "Replace" :"1047052F035F53425F50434930475050375B82450455505858"
            }
        )

    def get_unique_name(self,name,target_folder,name_append="-Patched"):
        # Get a new file name in the Results folder so we don't override the original
        name = os.path.basename(name)
        ext  = "" if not "." in name else name.split(".")[-1]
        if ext: name = name[:-len(ext)-1]
        if name_append: name = name+str(name_append)
        check_name = ".".join((name,ext)) if ext else name
        if not os.path.exists(os.path.join(target_folder,check_name)):
            return check_name
        # We need a unique name
        num = 1
        while True:
            check_name = "{}-{}".format(name,num)
            if ext: check_name += "."+ext
            if not os.path.exists(os.path.join(target_folder,check_name)):
                return check_name
            num += 1 # Increment our counter

    def load_dsdt(self,path):
        self.u.head("Loading DSDT")
        print("")
        print("Loading {}...".format(path))
        print("")
        if not os.path.isfile(path):
            print("File does not exist!")
            print("")
            self.u.grab("Press [enter] to return...")
        if self.d.load(path): return path
        # Didn't load
        print("Checking available pre-patches...")
        print("Loading {} into memory...".format(os.path.basename(path)))
        with open(path,"rb") as f:
            d = f.read()
        res = self.d.check_output(self.output)
        target_name = self.get_unique_name(os.path.basename(path),res,name_append="-Patched")
        target_path = os.path.join(res,target_name)
        patches = []
        print("Iterating patches...")
        for p in self.pre_patches:
            if not all((x in p for x in ("PrePatch","Comment","Find","Replace"))): continue
            print(" - {}".format(p["PrePatch"]))
            find = binascii.unhexlify(p["Find"])
            if d.count(find) == 1:
                patches.append(p) # Retain the patch
                repl = binascii.unhexlify(p["Replace"])
                print(" --> Located - applying...")
                d = d.replace(find,repl) # Replace it in memory
                with open(target_path,"wb") as f:
                    f.write(d) # Write the updated file
                # Attempt to load again
                if self.d.load(target_path):
                    # We got it to load - let's write the patches
                    print("\nDecompiled successfully!\n")
                    self.make_plist(None, None, patches)
                    print("\n!! Patches applied to modified file in Results folder:\n   {}".format(target_name))
                    self.patch_warn()
                    self.u.grab("Press [enter] to continue...")
                    return path
        # No patches worked - write the original back
        print("Removing patched file...")
        try: os.remove(target_path)
        except: print(" - Failed to remove!")
        print("\n{} could not be decompiled!".format(os.path.basename(path)))
        print("")
        self.u.grab("Press [enter] to return...")

    def select_dsdt(self):
        while True:
            self.u.head("Select DSDT")
            print(" ")
            print("M. Main")
            print("Q. Quit")
            print(" ")
            dsdt = self.u.grab("Please drag and drop a DSDT.aml or origin folder here:  ")
            if dsdt.lower() == "m":
                return self.dsdt
            if dsdt.lower() == "q":
                self.u.custom_quit()
            out = self.u.check_path(dsdt)
            if not out: continue
            # Got a DSDT, try to load it
            return self.load_dsdt(out)

    def ensure_dsdt(self):
        if self.dsdt and self.d.dsdt:
            # Got it already
            return True
        # Need to prompt
        self.dsdt = self.select_dsdt()
        if self.dsdt and self.d.dsdt:
            return True
        return False

    def write_ssdt(self, ssdt_name, ssdt):
        res = self.d.check_output(self.output)
        dsl_path = os.path.join(res,ssdt_name+".dsl")
        aml_path = os.path.join(res,ssdt_name+".aml")
        iasl_path = self.d.iasl
        with open(dsl_path,"w") as f:
            f.write(ssdt)
        print("Compiling...")
        out = self.r.run({"args":[iasl_path, dsl_path]})
        if out[2] != 0:
            print(" - {}".format(out[1]))
            self.re.reveal(dsl_path,True)
            return False
        else:
            self.re.reveal(aml_path,True)
        return True

    def ensure_path(self, plist_data, path_list, final_type = list):
        if not path_list: return plist_data
        last = plist_data
        for index,path in enumerate(path_list):
            if not path in last:
                if index >= len(path_list)-1:
                    last[path] = final_type()
                else:
                    last[path] = {}
            last = last[path]
        return plist_data
    
    def make_plist(self, oc_acpi, cl_acpi, patches, replace=False):
        # if not len(patches): return # No patches to add - bail
        repeat = False
        print("Building patches_OC and patches_Clover plists...")
        output = self.d.check_output(self.output)
        oc_plist = {}
        cl_plist = {}

        # Check for the plists
        if os.path.isfile(os.path.join(output,"patches_OC.plist")): 
            e = os.path.join(output,"patches_OC.plist")
            with open(e, "rb") as f:
                oc_plist = plist.load(f)
        if os.path.isfile(os.path.join(output,"patches_Clover.plist")): 
            e = os.path.join(output,"patches_Clover.plist")
            with open(e,"rb") as f:
                cl_plist = plist.load(f)
        
        # Ensure all the pathing is where it needs to be
        if oc_acpi: oc_plist = self.ensure_path(oc_plist,("ACPI","Add"))
        if cl_acpi: cl_plist = self.ensure_path(cl_plist,("ACPI","SortedOrder"))
        if patches:
            oc_plist = self.ensure_path(oc_plist,("ACPI","Patch"))
            cl_plist = self.ensure_path(cl_plist,("ACPI","DSDT","Patches"))

        # Add the .aml references
        if replace: # Remove any conflicting entries
            if oc_acpi:
                oc_plist["ACPI"]["Add"] = [x for x in oc_plist["ACPI"]["Add"] if oc_acpi["Path"] != x["Path"]]
            if cl_acpi:
                cl_plist["ACPI"]["SortedOrder"] = [x for x in cl_plist["ACPI"]["SortedOrder"] if cl_acpi != x]
        if oc_acpi: # Make sure we have something
            if any(oc_acpi["Path"] == x["Path"] for x in oc_plist["ACPI"]["Add"]):
                print(" -> Add \"{}\" already in OC plist!".format(oc_acpi["Path"]))
            else:
                oc_plist["ACPI"]["Add"].append(oc_acpi)
        if cl_acpi: # Make sure we have something
            if cl_acpi in cl_plist["ACPI"]["SortedOrder"]:
                print(" -> \"{}\" already in Clover plist!".format(cl_acpi))
            else:
                cl_plist["ACPI"]["SortedOrder"].append(cl_acpi)

        # Iterate the patches
        for p in patches:
            ocp = self.get_oc_patch(p)
            cp  = self.get_clover_patch(p)
            if replace: # Remove any conflicting entries
                oc_plist["ACPI"]["Patch"] = [x for x in oc_plist["ACPI"]["Patch"] if ocp["Find"] != x["Find"] and ocp["Replace"] != x["Replace"]]
                cl_plist["ACPI"]["DSDT"]["Patches"] = [x for x in cl_plist["ACPI"]["DSDT"]["Patches"] if cp["Find"] != x["Find"] and cp["Replace"] != x["Replace"]]
            if any(x["Find"] == ocp["Find"] and x["Replace"] == ocp["Replace"] for x in oc_plist["ACPI"]["Patch"]):
                print(" -> Patch \"{}\" already in OC plist!".format(p["Comment"]))
            else:
                print(" -> Adding Patch \"{}\" to OC plist!".format(p["Comment"]))
                oc_plist["ACPI"]["Patch"].append(ocp)
            if any(x["Find"] == cp["Find"] and x["Replace"] == cp["Replace"] for x in cl_plist["ACPI"]["DSDT"]["Patches"]):
                print(" -> Patch \"{}\" already in Clover plist!".format(p["Comment"]))
            else:
                print(" -> Adding Patch \"{}\" to Clover plist!".format(p["Comment"]))
                cl_plist["ACPI"]["DSDT"]["Patches"].append(cp)         
        # Write the plists if we have something to write
        if oc_plist:
            with open(os.path.join(output,"patches_OC.plist"),"wb") as f:
                plist.dump(oc_plist,f)
        if cl_plist:
            with open(os.path.join(output,"patches_Clover.plist"),"wb") as f:
                plist.dump(cl_plist,f)

    def patch_warn(self):
        # Warn users to ensure they merge the patches_XX.plist contents with their config.plist
        print("\n\u001b[41;1m!! WARNING !!\u001b[0m  Make sure you merge the contents of patches_[OC/Clover].plist")
        print("               with your config.plist!\n")

    def fake_ec(self, laptop = False):
        rename = False
        if not self.ensure_dsdt():
            return
        self.u.head("Fake EC")
        print("")
        print("Locating PNP0C09 (EC) devices...")
        ec_list = self.d.get_device_paths_with_hid("PNP0C09")
        ec_to_patch  = []
        patches = []
        lpc_name = None
        if len(ec_list):
            lpc_name = ".".join(ec_list[0][0].split(".")[:-1])
            print(" - Got {}".format(len(ec_list)))
            print(" - Validating...")
            for x in ec_list:
                device = x[0]
                print(" --> {}".format(device))
                if device.split(".")[-1] == "EC":
                    if laptop:
                        print(" ----> Named EC device located - no fake needed.")
                        print("")
                        self.u.grab("Press [enter] to return to main menu...")
                        return
                    print(" ----> EC called EC. Renaming")
                    device = ".".join(device.split(".")[:-1]+["EC0"])
                    rename = True
                scope = "\n".join(self.d.get_scope(x[1],strip_comments=True))
                # We need to check for _HID, _CRS, and _GPE
                if all((y in scope for y in ["_HID","_CRS","_GPE"])):
                    print(" ----> Valid EC Device")
                    sta = self.d.get_method_paths(device+"._STA")
                    if len(sta):
                        print(" ----> Contains _STA method. Skipping")
                        continue
                    if not laptop:
                        ec_to_patch.append(device)
                else:
                    print(" ----> NOT Valid EC Device")
        else:
            print(" - None found - only needs a Fake EC device")
        print("Locating LPC(B)/SBRG...")
        if lpc_name == None:
            for x in ("LPCB", "LPC0", "LPC", "SBRG", "PX40"):
                try:
                    lpc_name = self.d.get_device_paths(x)[0][0]
                    break
                except: pass
        if not lpc_name:
            print(" - Could not locate LPC(B)! Aborting!")
            print("")
            self.u.grab("Press [enter] to return to main menu...")
            return
        print(" - Found {}".format(lpc_name))
        comment = "SSDT-EC"
        if rename == True:
            patches.append({"Comment":"EC to EC0","Find":"45435f5f","Replace":"4543305f"})
            comment += " (Needs EC to EC0 rename)"
        oc = {"Comment":comment,"Enabled":True,"Path":"SSDT-EC.aml"}
        self.make_plist(oc, "SSDT-EC.aml", patches)
        print("Creating SSDT-EC...")
        ssdt = """
DefinitionBlock ("", "SSDT", 2, "CORP ", "SsdtEC", 0x00001000)
{
    External ([[LPCName]], DeviceObj)
""".replace("[[LPCName]]",lpc_name)
        for x in ec_to_patch:
            ssdt += "    External ({}, DeviceObj)\n".format(x)
        # Walk them again and add the _STAs
        for x in ec_to_patch:
            ssdt += """
    Scope ([[ECName]])
    {
        Method (_STA, 0, NotSerialized)  // _STA: Status
        {
            If (_OSI ("Darwin"))
            {
                Return (0)
            }
            Else
            {
                Return (0x0F)
            }
        }
    }
""".replace("[[LPCName]]",lpc_name).replace("[[ECName]]",x)
        # Create the faked EC
        ssdt += """
    Scope ([[LPCName]])
    {
        Device (EC)
        {
            Name (_HID, "ACID0001")  // _HID: Hardware ID
            Method (_STA, 0, NotSerialized)  // _STA: Status
            {
                If (_OSI ("Darwin"))
                {
                    Return (0x0F)
                }
                Else
                {
                    Return (Zero)
                }
            }
        }
    }
}""".replace("[[LPCName]]",lpc_name)
        self.write_ssdt("SSDT-EC",ssdt)
        print("")
        print("Done.")
        self.patch_warn()
        self.u.grab("Press [enter] to return...")

    def plugin_type(self):
        if not self.ensure_dsdt():
            return
        self.u.head("Plugin Type")
        print("")
        ssdt_name = "SSDT-PLUG"
        print("Determining CPU name scheme...")
        try: cpu_name = self.d.get_processor_paths("")[0][0]
        except: cpu_name = None
        if cpu_name:
            print(" - Found {}".format(cpu_name))
            oc = {"Comment":"Sets plugin-type to 1 on first Processor object","Enabled":True,"Path":ssdt_name+".aml"}
            print("Creating SSDT-PLUG...")
            ssdt = """//
// Based on the sample found at https://github.com/acidanthera/OpenCorePkg/blob/master/Docs/AcpiSamples/SSDT-PLUG.dsl
//
DefinitionBlock ("", "SSDT", 2, "CORP", "CpuPlug", 0x00003000)
{
    External ([[CPUName]], ProcessorObj)
    Scope ([[CPUName]])
    {
        If (_OSI ("Darwin")) {
            Method (_DSM, 4, NotSerialized)  // _DSM: Device-Specific Method
            {
                If (!Arg2)
                {
                    Return (Buffer (One)
                    {
                        0x03
                    })
                }
                Return (Package (0x02)
                {
                    "plugin-type", 
                    One
                })
            }
        }
    }
}""".replace("[[CPUName]]",cpu_name)
        else:
            ssdt_name += "-ALT"
            print("No Processor objects found...")
            print("Checking for ACPI0007 devices...")
            procs = self.d.get_device_paths_with_hid(hid="ACPI0007")
            if not procs:
                print("Could not find any Processor objects or ACPI0007 devices!")
                print("")
                self.u.grab("Press [enter] to return...")
                return
            parent = procs[0][0].split(".")[0]
            print("Got {:,} with parent {}, iterating...".format(len(procs),parent))
            proc_list = []
            for proc in procs:
                print(" - Checking {}...".format(proc[0].split(".")[-1]))
                uid = self.d.get_path_of_type(obj_type="Name",obj=proc[0]+"._UID")
                if not uid:
                    print(" --> Not found!  Skipping...")
                    continue
                # Let's get the actual _UID value
                try:
                    _uid = self.d.dsdt_lines[uid[0][1]].split("_UID, ")[1].split(")")[0]
                    print(" --> _UID: {}".format(_uid))
                    proc_list.append((proc[0],_uid))
                except:
                    print(" --> Not found!  Skipping...")
            if not proc_list:
                print("No valid processor devices found!  Aborting...")
                print("")
                self.u.grab("Press [enter] to return...")
                return
            print("Iterating {:,} valid processor device{}...".format(len(proc_list),"" if len(proc_list)==1 else "s"))
            ssdt = """//
// Based on the sample found at https://github.com/acidanthera/OpenCorePkg/blob/master/Docs/AcpiSamples/Source/SSDT-PLUG-ALT.dsl
//
DefinitionBlock ("", "SSDT", 2, "CORP", "CpuPlugA", 0x00003000)
{
    External ([[parent]], DeviceObj)

    Scope ([[parent]])
    {""".replace("[[parent]]",parent)
            # Walk the processor objects, and add them to the SSDT
            for i,proc_uid in enumerate(proc_list):
                proc,uid = proc_uid
                adr = hex(i)[2:].upper()
                name = "CP00"[:-len(adr)]+adr
                ssdt+="""
        Processor ([[name]], [[uid]], 0x00000510, 0x06)
        {
            // [[proc]]
            Name (_HID, "ACPI0007" /* Processor Device */)  // _HID: Hardware ID
            Name (_UID, [[uid]])
            Method (_STA, 0, NotSerialized)  // _STA: Status
            {
                If (_OSI ("Darwin"))
                {
                    Return (0x0F)
                }
                Else
                {
                    Return (Zero)
                }
            }""".replace("[[name]]",name).replace("[[uid]]",uid).replace("[[proc]]",proc)
                if i == 0: # Got the first, add plugin-type as well
                    ssdt += """
            Method (_DSM, 4, NotSerialized)
            {
                If (LEqual (Arg2, Zero)) {
                    Return (Buffer (One) { 0x03 })
                }

                Return (Package (0x02)
                {
                    "plugin-type",
                    One
                })
            }"""
                # Close up the SSDT
                ssdt += """
        }"""
            ssdt += """
    }
}"""
            oc = {"Comment":"Redefines modern CPU Devices as legacy Processor objects and sets plugin-type to 1 on the first","Enabled":True,"Path":ssdt_name+".aml"}
        self.make_plist(oc, ssdt_name+".aml", ())
        self.write_ssdt(ssdt_name,ssdt)
        print("")
        print("Done.")
        self.patch_warn()
        self.u.grab("Press [enter] to return...")

    def list_irqs(self):
        # Walks the DSDT keeping track of the current device and
        # saving the IRQNoFlags if found
        devices = {}
        current_device = None
        current_hid = None
        irq = False
        last_irq = False
        irq_index = 0
        for index,line in enumerate(self.d.dsdt_lines):
            if self.d.is_hex(line):
                # Skip all hex lines
                continue
            if irq:
                # Get the values
                num = line.split("{")[1].split("}")[0].replace(" ","")
                num = "#" if not len(num) else num
                if current_device in devices:
                    if last_irq: # In a row
                        devices[current_device]["irq"] += ":"+num
                    else: # Skipped at least one line
                        irq_index = self.d.find_next_hex(index)[1]
                        devices[current_device]["irq"] += "-"+str(irq_index)+"|"+num
                else:
                    irq_index = self.d.find_next_hex(index)[1]
                    devices[current_device] = {"irq":str(irq_index)+"|"+num}
                irq = False
                last_irq = True
            elif "Device (" in line:
                # Check if we retain the _HID here
                if current_device and current_device in devices and current_hid:
                    # Save it
                    devices[current_device]["hid"] = current_hid
                last_irq = False
                current_hid = None
                try: current_device = line.split("(")[1].split(")")[0]
                except:
                    current_device = None
                    continue
            elif "_HID, " in line and current_device:
                try: current_hid = line.split('"')[1]
                except: pass
            elif "IRQNoFlags" in line and current_device:
                # Next line has our interrupts
                irq = True
            # Check if just a filler line
            elif len(line.replace("{","").replace("}","").replace("(","").replace(")","").replace(" ","").split("//")[0]):
                # Reset last IRQ as it's not in a row
                last_irq = False
        # Retain the final _HID if needed
        if current_device and current_device in devices and current_hid:
            devices[current_device]["hid"] = current_hid
        return devices

    def get_hex_from_irqs(self, irq, rem_irq = None):
        # We need to search for a few different types:
        #
        # 22 XX XX 22 XX XX 22 XX XX (multiples on different lines)
        # 22 XX XX (summed multiples in the same bracket - {0,8,11})
        # 22 XX XX (single IRQNoFlags entry)
        # 
        # Can end with 79 [00] (end of method), 86 09 (middle of method) or 47 01 (unknown)
        lines = []
        remd  = []
        for a in irq.split("-"):
            index,i = a.split("|") # Get the index
            index = int(index)
            find = self.get_int_for_line(i)
            repl = [0]*len(find)
            # Now we need to verify if we're patching *all* IRQs, or just some specifics
            if rem_irq:
                repl = [x for x in find]
                matched = []
                for x in rem_irq:
                    # Get the int
                    rem = self.convert_irq_to_int(x)
                    repl1 = [y&(rem^0xFFFF) if y >= rem else y for y in repl]
                    if repl1 != repl:
                        # Changes were made
                        remd.append(x)
                    repl = [y for y in repl1]
            # Get the hex
            d = {
                "irq":i,
                "find": "".join(["22"+self.d.get_hex_from_int(x) for x in find]),
                "repl": "".join(["22"+self.d.get_hex_from_int(x) for x in repl]),
                "remd": remd,
                "index": index
                }
            d["changed"] = not (d["find"]==d["repl"])
            lines.append(d)
        return lines
        
    def get_int_for_line(self, irq):
        irq_list = []
        for i in irq.split(":"):
            irq_list.append(self.same_line_irq(i))
        return irq_list

    def convert_irq_to_int(self, irq):
        b = "0"*(16-irq)+"1"+"0"*(irq)
        return int(b,2)

    def same_line_irq(self, irq):
        # We sum the IRQ values and return the int
        total = 0
        for i in irq.split(","):
            if i == "#":
                continue # Null value
            try: i=int(i)
            except: continue # Not an int
            if i > 15 or i < 0:
                continue # Out of range
            total = total | self.convert_irq_to_int(i)
        return total

    def get_all_irqs(self, irq):
        irq_list = []
        for a in irq.split("-"):
            i = a.split("|")[1]
            for x in i.split(":"):
                for y in x.split(","):
                    if y == "#":
                        continue
                    irq_list.append(int(y))
        return irq_list

    def get_data(self, data):
        if sys.version_info >= (3, 0):
            return data
        else:
            return plistlib.Data(data)

    def get_clover_patch(self, patch):
        return {
            "Comment": patch["Comment"],
            "Disabled": patch.get("Disabled",False),
            "Find": self.get_data(self.d.get_hex_bytes(patch["Find"])),
            "Replace": self.get_data(self.d.get_hex_bytes(patch["Replace"]))
        }

    def get_oc_patch(self, patch):
        zero = self.get_data(self.d.get_hex_bytes("00000000"))
        return {
            "Base": "",
            "BaseSkip": 0,
            "Comment": patch["Comment"],
            "Count": 0,
            "Enabled": patch.get("Enabled",True),
            "Find": self.get_data(self.d.get_hex_bytes(patch["Find"])),
            "Limit": 0,
            "Mask": self.get_data(b""),
            "OemTableId": zero,
            "Replace": self.get_data(self.d.get_hex_bytes(patch["Replace"])),
            "ReplaceMask": self.get_data(b""),
            "Skip": 0,
            "TableLength": 0,
            "TableSignature": zero
        }

    def get_irq_choice(self, irqs):
        hid_pad = max((len(irqs[x].get("hid","")) for x in irqs))
        names_and_hids = ["PIC","IPIC","TMR","TIMR","RTC","RTC0","RTC1","PNPC0000","PNP0100","PNP0B00"]
        defaults = [x for x in irqs if x.upper() in names_and_hids or irqs[x].get("hid","").upper() in names_and_hids]
        while True:
            pad = 24
            self.u.head("Select IRQs To Nullify")
            print("")
            print("Current Legacy IRQs:")
            print("")
            if not len(irqs):
                print(" - None Found")
            pad+=len(irqs) if len(irqs) else 1
            for x in irqs:
                if not hid_pad:
                    print(" {} {}: {}".format(
                        "*" if x.upper() in names_and_hids else " ",
                        x.rjust(4," "),
                        self.get_all_irqs(irqs[x]["irq"])
                    ))
                else:
                    print(" {} {} {}: {}".format(
                        "*" if x.upper() in names_and_hids or irqs[x].get("hid","").upper() in names_and_hids else " ",
                        x.rjust(4," "),
                        ("- "+irqs[x].get("hid","").rjust(hid_pad," ")) if irqs[x].get("hid") else "".rjust(hid_pad+2," "),
                        self.get_all_irqs(irqs[x]["irq"])
                    ))
            print("")
            print("C. Only Conflicting IRQs from Legacy Devices ({} from * devices)".format(",".join([str(x) for x in self.target_irqs]) if len(self.target_irqs) else "None"))
            print("O. Only Conflicting IRQs ({})".format(",".join([str(x) for x in self.target_irqs]) if len(self.target_irqs) else "None"))
            print("L. Legacy IRQs (from * devices)")
            print("N. None")
            print("")
            print("M. Main Menu")
            print("Q. Quit")
            print("")
            print("* Indicates a typically troublesome device")
            print("You can also type your own list of Devices and IRQs")
            print("The format is DEV1:IRQ1,IRQ2 DEV2:IRQ3,IRQ4")
            print("You can omit the IRQ# to remove all from that device (DEV1: DEV2:1,2,3)")
            print("For example, to remove IRQ 0 from RTC, all from IPIC, and 8 and 11 from TMR:\n")
            print("RTC:0 IPIC: TMR:8,11")
            self.u.resize(self.w, max(pad,self.h))
            menu = self.u.grab("Please select an option (default is C):  ")
            if not len(menu):
                menu = "c"
            if menu.lower() == "m": return None
            elif menu.lower() == "q":
                self.u.resize(self.w,self.h)
                self.u.custom_quit()
            d = {}
            if menu.lower() == "n":
                pass # Don't populate d at all
            elif menu.lower() == "o":
                for x in irqs:
                    d[x] = self.target_irqs
            elif menu.lower() == "l":
                for x in defaults:
                    d[x] = []
            elif menu.lower() == "c":
                for x in defaults:
                    d[x] = self.target_irqs
            else:
                # User supplied
                for i in menu.split(" "):
                    if not len(i):
                        continue
                    try:
                        name,val = i.split(":")
                        val = [int(x) for x in val.split(",") if len(x)]
                    except Exception as e:
                        # Incorrectly formatted
                        print("!! Incorrect Custom IRQ List Format !!\n - {}".format(e))
                        d = None
                        break
                    d[name.upper()] = val
                if d == None:
                    continue
            self.u.resize(self.w,self.h)
            return d

    def fix_hpet(self):
        if not self.ensure_dsdt():
            return
        self.u.head("Fix HPET")
        print("")
        print("Locating PNP0103 (HPET) devices...")
        hpets = self.d.get_device_paths_with_hid("PNP0103")
        hpet_fake = not hpets
        patches = []
        hpet_sta = False
        sta = None
        if hpets:
            name = hpets[0][0]
            print(" - Located at {}".format(name))
            # Let's locate any _STA methods
            sta = self.get_sta_var(var=None,dev_hid="PNP0103",dev_name="HPET",log_locate=False)
            if sta.get("patches"):
                hpet_sta = True
                patches.extend(sta.get("patches",[]))
            print("Locating HPET's _CRS Method/Name...")
            hpet = self.d.get_method_paths(name+"._CRS") or self.d.get_name_paths(name+"._CRS")
            if not hpet:
                print(" - Could not locate {}._CRS! Aborting!".format(name))
                # Check for XCRS to see if the rename is already applied
                if self.d.get_method_paths(name+".XCRS") or self.d.get_name_paths(name+".XCRS"):
                    print(" --> Appears to already be named XCRS!")
                print("")
                self.u.grab("Press [enter] to return to main menu...")
                return
            print(" - Located at {}._CRS".format(name))
            crs_index = self.d.find_next_hex(hpet[0][1])[1]
            print(" - Found at index {}".format(crs_index))
            print(" - Type: {}".format(hpet[0][-1]))
            # Let's find the Memory32Fixed portion within HPET's _CRS method
            print(" - Checking for Memory32Fixed...")
            mem_base = mem_length = primed = None
            for line in self.d.get_scope(hpets[0][1],strip_comments=True):
                if "Memory32Fixed (" in line:
                    primed = True
                    continue
                if not primed:
                    continue
                elif ")" in line: # Reached the end of the scope
                    break
                # We're primed, and not at the end - let's try to get the base and length
                try:
                    val = line.strip().split(",")[0].replace("Zero","0x0").replace("One","0x1")
                    check = int(val,16)
                except:
                    # Couldn't convert to an int - likely using vars, fall back to defaults
                    print(" --> Could not convert Base or Length to Integer!")
                    break
                # Set them in order
                if mem_base is None:
                    mem_base = val
                else:
                    mem_length = val
                    break # Leave after we get both values
            # Check if we found the values
            got_mem = mem_base and mem_length
            if got_mem:
                print(" --> Got {} -> {}".format(mem_base,mem_length))
            else:
                mem_base = "0xFED00000"
                mem_length = "0x00000400"
                print(" --> Not located!")
                print(" --> Using defaults {} -> {}".format(mem_base,mem_length))
            crs  = "5F435253"
            xcrs = "58435253"
            padl,padr = self.d.get_shortest_unique_pad(crs, crs_index)
            patches.append({"Comment":"{} _CRS to XCRS Rename".format(name.split(".")[-1].lstrip("\\")),"Find":padl+crs+padr,"Replace":padl+xcrs+padr})
        else:
            print(" - None located!")
            print(" - Locating LPC(B)/SBRG...")
            ec_list = self.d.get_device_paths_with_hid("PNP0C09")
            name = None
            if len(ec_list):
                name = ".".join(ec_list[0][0].split(".")[:-1])
            if name == None:
                for x in ("LPCB", "LPC0", "LPC", "SBRG", "PX40"):
                    try:
                        name = self.d.get_device_paths(x)[0][0]
                        break
                    except: pass
            if not name:
                print(" - Could not locate LPC(B)! Aborting!")
                print("")
                self.u.grab("Press [enter] to return to main menu...")
                return
        devs = self.list_irqs()
        target_irqs = self.get_irq_choice(devs)
        if target_irqs is None: return # Bailed, going to the main menu
        self.u.head("Creating IRQ Patches")
        print("")
        if not hpet_fake:
            print(" - {} _CRS to XCRS Rename:".format(name.split(".")[-1].lstrip("\\")))
            print("      Find: {}".format(padl+crs+padr))
            print("   Replace: {}".format(padl+xcrs+padr))
            print("")
        print("Checking IRQs...")
        print("")
        if not devs:
            print(" - Nothing to patch!")
            print("")
        # Let's apply patches as we go
        saved_dsdt = self.d.dsdt_raw
        unique_patches  = {}
        generic_patches = []
        for dev in devs:
            if not dev in target_irqs:
                continue
            irq_patches = self.get_hex_from_irqs(devs[dev]["irq"],target_irqs[dev])
            i = [x for x in irq_patches if x["changed"]]
            for a,t in enumerate(i):
                if not t["changed"]:
                    # Nothing patched - skip
                    continue
                # Try our endings here - 7900, 8609, and 4701 - also allow for up to 8 chars of pad (thanks MSI)
                matches = re.findall("("+t["find"]+"(.{0,8})(7900|4701|8609))",self.d.get_hex_starting_at(t["index"])[0])
                if not len(matches):
                    print("Missing IRQ Patch ending for {} ({})! Skipping...".format(dev,t["find"]))
                    continue
                if len(matches) > 1:
                    # Found too many matches!
                    # Add them all as find/replace entries
                    for x in matches:
                        generic_patches.append({
                            "remd":",".join([str(y) for y in set(t["remd"])]),
                            "orig":t["find"],
                            "find":t["find"]+"".join(x[1:]),
                            "repl":t["repl"]+"".join(x[1:])
                        })
                    continue
                ending = "".join(matches[0][1:])
                padl,padr = self.d.get_shortest_unique_pad(t["find"]+ending, t["index"])
                t_patch = padl+t["find"]+ending+padr
                r_patch = padl+t["repl"]+ending+padr
                if not dev in unique_patches:
                    unique_patches[dev] = []
                unique_patches[dev].append({
                    "dev":dev,
                    "remd":",".join([str(y) for y in set(t["remd"])]),
                    "orig":t["find"],
                    "find":t_patch,
                    "repl":r_patch
                })
        # Walk the unique patches if any
        if len(unique_patches):
            for x in unique_patches:
                for i,p in enumerate(unique_patches[x]):
                    patch_name = "{} IRQ {} Patch".format(x, p["remd"])
                    if len(unique_patches[x]) > 1:
                        patch_name += " - {} of {}".format(i+1, len(unique_patches[x]))
                    patches.append({"Comment":patch_name,"Find":p["find"],"Replace":p["repl"]})
                    print(" - {}".format(patch_name))
                    print("      Find: {}".format(p["find"]))
                    print("   Replace: {}".format(p["repl"]))
                    print("")
        # Walk the generic patches if any
        if len(generic_patches):
            generic_set = [] # Make sure we don't repeat find values
            for x in generic_patches:
                if x in generic_set:
                    continue
                generic_set.append(x)
            print("The following may not be unique and are disabled by default!")
            print("")
            for i,x in enumerate(generic_set):
                patch_name = "Generic IRQ Patch {} of {} - {} - {}".format(i+1,len(generic_set),x["remd"],x["orig"])
                patches.append({"Comment":patch_name,"Find":x["find"],"Replace":x["repl"],"Disabled":True,"Enabled":False})
                print(" - {}".format(patch_name))
                print("      Find: {}".format(x["find"]))
                print("   Replace: {}".format(x["repl"]))
                print("")
        # Restore the original DSDT in memory
        self.d.dsdt_raw = saved_dsdt
        oc = {"Comment":"{} _CRS (Needs _CRS to XCRS Rename)".format(name.split(".")[-1].lstrip("\\")),"Enabled":True,"Path":"SSDT-HPET.aml"}
        self.make_plist(oc, "SSDT-HPET.aml", patches)
        print("Creating SSDT-HPET...")
        if hpet_fake:
            ssdt = """// Fake HPET device
//
DefinitionBlock ("", "SSDT", 2, "CORP", "HPET", 0x00000000)
{
    External ([[name]], DeviceObj)

    Scope ([[name]])
    {
        Device (HPET)
        {
            Name (_HID, EisaId ("PNP0103") /* HPET System Timer */)  // _HID: Hardware ID
            Name (_CID, EisaId ("PNP0C01") /* System Board */)  // _CID: Compatible ID
            Method (_STA, 0, NotSerialized)  // _STA: Status
            {
                If (_OSI ("Darwin"))
                {
                    Return (0x0F)
                }
                Else
                {
                    Return (Zero)
                }
            }
            Name (_CRS, ResourceTemplate ()  // _CRS: Current Resource Settings
            {
                IRQNoFlags ()
                    {0,8,11}
                Memory32Fixed (ReadWrite,
                    0xFED00000,         // Address Base
                    0x00000400,         // Address Length
                    )
            })
        }
    }
}""".replace("[[name]]",name)
        else:
            ssdt = """//
// Supplementary HPET _CRS from Goldfish64
// Requires the HPET's _CRS to XCRS rename
//
DefinitionBlock ("", "SSDT", 2, "CORP", "HPET", 0x00000000)
{
    External ([[name]], DeviceObj)
    External ([[name]].XCRS, [[type]])

    Scope ([[name]])
    {
        Name (BUFX, ResourceTemplate ()
        {
            IRQNoFlags ()
                {0,8,11}
            Memory32Fixed (ReadWrite,
                // [[mem]]
                [[mem_base]],         // Address Base
                [[mem_length]],         // Address Length
            )
        })
        Method (_CRS, 0, Serialized)  // _CRS: Current Resource Settings
        {
            // Return our buffer if booting macOS or the XCRS method
            // no longer exists for some reason
            If (_OSI ("Darwin") || !CondRefOf ([[name]].XCRS))
            {
                Return (BUFX)
            }
            // Not macOS and XCRS exists - return its result
            Return ([[name]].XCRS[[method]])
        }""" \
    .replace("[[name]]",name) \
    .replace("[[type]]","MethodObj" if hpet[0][-1] == "Method" else "BuffObj") \
    .replace("[[mem]]","Base/Length pulled from DSDT" if got_mem else "Default Base/Length - verify with your DSDT!") \
    .replace("[[mem_base]]",mem_base) \
    .replace("[[mem_length]]",mem_length) \
    .replace("[[method]]"," ()" if hpet[0][-1]=="Method" else "")
            if hpet_sta:
                # Inject our external reference to the renamed XSTA method
                ssdt_parts = []
                external = False
                for line in ssdt.split("\n"):
                    if "External (" in line: external = True
                    elif external:
                        ssdt_parts.append("    External ({}.XSTA, {})".format(name,sta["sta_type"]))
                        external = False
                    ssdt_parts.append(line)
                ssdt = "\n".join(ssdt_parts)
                # Add our method
                ssdt += """
        Method (_STA, 0, NotSerialized)  // _STA: Status
        {
            // Return 0x0F if booting macOS or the XSTA method
            // no longer exists for some reason
            If (_OSI ("Darwin") || !CondRefOf ([[name]].XSTA))
            {
                Return (0x0F)
            }
            // Not macOS and XSTA exists - return its result
            Return ([[name]].XSTA[[called]])
        }""".replace("[[name]]",name).replace("[[called]]"," ()" if sta["sta_type"]=="MethodObj" else "")
            ssdt += """
    }
}"""
        self.write_ssdt("SSDT-HPET",ssdt)
        print("")
        print("Done.")
        self.patch_warn()
        self.u.grab("Press [enter] to return...")

    def ssdt_pmc(self):
        if not self.ensure_dsdt():
            return
        self.u.head("SSDT PMC")
        print("")
        print("Locating LPC(B)/SBRG...")
        ec_list = self.d.get_device_paths_with_hid("PNP0C09")
        lpc_name = None
        if len(ec_list):
            lpc_name = ".".join(ec_list[0][0].split(".")[:-1])
        if lpc_name == None:
            for x in ("LPCB", "LPC0", "LPC", "SBRG", "PX40"):
                try:
                    lpc_name = self.d.get_device_paths(x)[0][0]
                    break
                except: pass
        if not lpc_name:
            print(" - Could not locate LPC(B)! Aborting!")
            print("")
            self.u.grab("Press [enter] to return to main menu...")
            return
        print(" - Found {}".format(lpc_name))
        oc = {"Comment":"PMCR for native 300-series NVRAM","Enabled":True,"Path":"SSDT-PMC.aml"}
        self.make_plist(oc, "SSDT-PMC.aml", ())
        print("Creating SSDT-PMC...")
        ssdt = """//
// SSDT-PMC source from Acidanthera
// Original found here: https://github.com/acidanthera/OpenCorePkg/blob/master/Docs/AcpiSamples/SSDT-PMC.dsl
//
// Uses the CORP name to denote where this was created for troubleshooting purposes.
//
DefinitionBlock ("", "SSDT", 2, "CORP", "PMCR", 0x00001000)
{
    External ([[LPCName]], DeviceObj)
    Scope ([[LPCName]])
    {
        Device (PMCR)
        {
            Name (_HID, EisaId ("APP9876"))  // _HID: Hardware ID
            Method (_STA, 0, NotSerialized)  // _STA: Status
            {
                If (_OSI ("Darwin"))
                {
                    Return (0x0B)
                }
                Else
                {
                    Return (Zero)
                }
            }
            Name (_CRS, ResourceTemplate ()  // _CRS: Current Resource Settings
            {
                Memory32Fixed (ReadWrite,
                    0xFE000000,         // Address Base
                    0x00010000,         // Address Length
                    )
            })
        }
    }
}""".replace("[[LPCName]]",lpc_name)
        self.write_ssdt("SSDT-PMC",ssdt)
        print("")
        print("Done.")
        self.patch_warn()
        self.u.grab("Press [enter] to return...")

    def get_sta_var(self,var="STAS",device=None,dev_hid="ACPI000E",dev_name="AWAC",log_locate=True):
        # Helper to check for a device, check for (and qualify) an _STA method,
        # and look for a specific variable in the _STA scope
        #
        # Returns a dict with device info - only "valid" parameter is
        # guaranteed.
        has_var = False
        patches = []
        root = None
        if device:
            dev_list = self.d.get_device_paths(device)
            if not len(dev_list):
                if log_locate: print(" - Could not locate {}".format(device))
                return {"value":False}
        else:
            if log_locate: print("Locating {} ({}) devices...".format(dev_hid,dev_name))
            dev_list = self.d.get_device_paths_with_hid(dev_hid)
            if not len(dev_list):
                if log_locate: print(" - Could not locate any {} devices".format(dev_hid))
                return {"valid":False}
        dev = dev_list[0]
        if log_locate: print(" - Found {}".format(dev[0]))
        root = dev[0].split(".")[0]
        print(" --> Verifying _STA...")
        # Check Method first - then Name
        sta_type = "MethodObj"
        sta  = self.d.get_method_paths(dev[0]+"._STA")
        xsta = self.d.get_method_paths(dev[0]+".XSTA")
        if not sta and not xsta:
            # Check for names
            sta_type = "IntObj"
            sta = self.d.get_name_paths(dev[0]+"._STA")
            xsta = self.d.get_name_paths(dev[0]+".XSTA")
        if xsta and not sta:
            print(" --> _STA already renamed to XSTA!  Skipping other checks...")
            print("     Please disable _STA to XSTA renames for this device, reboot, and try again.")
            print("")
            return {"valid":False,"break":True,"device":dev,"dev_name":dev_name,"dev_hid":dev_hid,"sta_type":sta_type}
        if sta:
            if var:
                scope = "\n".join(self.d.get_scope(sta[0][1],strip_comments=True))
                has_var = var in scope
                print(" --> {} {} variable".format("Has" if has_var else "Does NOT have",var))
        else:
            print(" --> No _STA method/name found")
        # Let's find out of we need a unique patch for _STA -> XSTA
        if sta and not has_var:
            print(" --> Generating _STA to XSTA rename")
            sta_index = self.d.find_next_hex(sta[0][1])[1]
            print(" ----> Found at index {}".format(sta_index))
            sta_hex  = "5F535441" # _STA
            xsta_hex = "58535441" # XSTA
            padl,padr = self.d.get_shortest_unique_pad(sta_hex, sta_index)
            patches.append({"Comment":"{} _STA to XSTA Rename".format(dev_name),"Find":padl+sta_hex+padr,"Replace":padl+xsta_hex+padr})
        return {"valid":True,"has_var":has_var,"sta":sta,"patches":patches,"device":dev,"dev_name":dev_name,"dev_hid":dev_hid,"root":root,"sta_type":sta_type}

    def ssdt_awac(self):
        if not self.ensure_dsdt():
            return
        self.u.head("SSDT RTCAWAC")
        print("")
        rtc_range_needed = False
        rtc_crs_type = None
        crs_lines = []
        lpc_name = None
        awac_dict = self.get_sta_var(var="STAS",dev_hid="ACPI000E",dev_name="AWAC")
        rtc_dict = self.get_sta_var(var="STAS",dev_hid="PNP0B00",dev_name="RTC")
        # At this point - we should have any info about our AWAC and RTC devices
        # we need.  Let's see if we need an RTC fake - then build the SSDT.
        if not rtc_dict.get("valid"):
            print(" - Fake needed!")
            print("Locating LPC(B)/SBRG...")
            ec_list = self.d.get_device_paths_with_hid("PNP0C09")
            if ec_list:
                lpc_name = ".".join(ec_list[0][0].split(".")[:-1])
            if lpc_name is None:
                for x in ("LPCB", "LPC0", "LPC", "SBRG", "PX40"):
                    try:
                        lpc_name = self.d.get_device_paths(x)[0][0]
                        break
                    except: pass
            if not lpc_name:
                print(" - Could not locate LPC(B)! Aborting!")
                print("")
                self.u.grab("Press [enter] to return to main menu...")
                return
        else:
            # Let's check if our RTC device has a _CRS variable - and if so, let's look for any skipped ranges
            print(" --> Checking for _CRS...")
            rtc_crs = self.d.get_method_paths(rtc_dict["device"][0]+"._CRS") or self.d.get_name_paths(rtc_dict["device"][0]+"._CRS")
            if rtc_crs:
                print(" ----> {}".format(rtc_crs[0][0]))
                rtc_crs_type = "MethodObj" if rtc_crs[0][-1] == "Method" else "BuffObj"
                print(" --> Checking RTC range...")
                last_adr = last_len = last_ind = None
                crs_scope = self.d.get_scope(rtc_crs[0][1])
                # Let's try and clean up the scope - it's often a jumbled mess
                pad_len = len(crs_scope[0])-len(crs_scope[0].lstrip())
                pad = crs_scope[0][:pad_len]
                fixed_scope = []
                for line in crs_scope:
                    if line.startswith(pad): # Got a full line - strip the pad, and save it
                        fixed_scope.append(line[pad_len:])
                    else: # Likely a part of the prior line
                        fixed_scope[-1] = fixed_scope[-1]+line
                for i,line in enumerate(fixed_scope):
                    if "IO (Decode16," in line:
                        # We have our start - get the the next line, and 4th line
                        try:
                            curr_adr = int(fixed_scope[i+1].strip().split(",")[0],16)
                            curr_len = int(fixed_scope[i+4].strip().split(",")[0],16)
                            curr_ind = i+4 # Save the value we may pad
                        except: # Bad values? Bail...
                            print(" ----> Failed to gather values - could not verify RTC range.")
                            rtc_range_needed = False
                            break
                        if last_adr is not None: # Compare our range values
                            adjust = curr_adr - (last_adr + last_len)
                            if adjust: # We need to increment the previous length by our adjust value
                                rtc_range_needed = True
                                print(" ----> Adjusting IO range {} length to {}".format(self.hexy(last_adr,pad_to=4),self.hexy(last_len+adjust,pad_to=2)))
                                try:
                                    hex_find,hex_repl = self.hexy(last_len,pad_to=2),self.hexy(last_len+adjust,pad_to=2)
                                    crs_lines[last_ind] = crs_lines[last_ind].replace(hex_find,hex_repl)
                                except:
                                    print(" ----> Failed to adjust values - could not verify RTC range.")
                                    rtc_range_needed = False
                                    break
                        # Save our last values
                        last_adr,last_len,last_ind = curr_adr,curr_len,curr_ind
                    crs_lines.append(line)
                if rtc_range_needed: # We need to generate a rename for _CRS -> XCRS
                    print(" --> Generating _CRS to XCRS rename...")
                    crs_index = self.d.find_next_hex(rtc_crs[0][1])[1]
                    print(" ----> Found at index {}".format(crs_index))
                    crs_hex  = "5F435253" # _CRS
                    xcrs_hex = "58435253" # XCRS
                    padl,padr = self.d.get_shortest_unique_pad(crs_hex, crs_index)
                    patches = rtc_dict.get("patches",[])
                    patches.append({"Comment":"{} _CRS to XCRS Rename".format(rtc_dict["dev_name"]),"Find":padl+crs_hex+padr,"Replace":padl+xcrs_hex+padr})
                    rtc_dict["patches"] = patches
                    rtc_dict["crs"] = True
            else:
                print(" ----> Not found")
        # Let's see if we even need an SSDT
        # Not required if AWAC is not present; RTC is present, doesn't have an STAS var, and doesn't have an _STA method, and no range fixes are needed
        if not awac_dict.get("valid") and rtc_dict.get("valid") and not rtc_dict.get("has_var") and not rtc_dict.get("sta") and not rtc_range_needed:
            print("")
            print("Valid PNP0B00 (RTC) device located and qualified, and no ACPI000E (AWAC) devices found.")
            print("No patching or SSDT needed.")
            print("")
            self.u.grab("Press [enter] to return to main menu...")
            return
        comment = "Incompatible AWAC Fix" if awac_dict.get("valid") else "RTC Fake" if not rtc_dict.get("valid") else "RTC Range Fix" if rtc_range_needed else "RTC Enable Fix"
        suffix  = []
        for x in (awac_dict,rtc_dict):
            if not x.get("valid"): continue
            val = ""
            if x.get("sta") and not x.get("has_var"):
                val = "{} _STA to XSTA".format(x["dev_name"])
            if x.get("crs"):
                val += "{} _CRS to XCRS".format(" and " if val else x["dev_name"])
            if val: suffix.append(val)
        if suffix:
            comment += " - Requires {} Rename".format(", ".join(suffix))
        # At this point - we need to do the following:
        # 1. Change STAS if needed
        # 2. Setup _STA with _OSI and call XSTA if needed
        # 3. Fake RTC if needed
        oc = {"Comment":comment,"Enabled":True,"Path":"SSDT-RTCAWAC.aml"}
        self.make_plist(oc, "SSDT-RTCAWAC.aml", awac_dict.get("patches",[])+rtc_dict.get("patches",[]), replace=True)
        print("Creating SSDT-RTCAWAC...")
        ssdt = """//
// Original sources from Acidanthera:
//  - https://github.com/acidanthera/OpenCorePkg/blob/master/Docs/AcpiSamples/SSDT-AWAC.dsl
//  - https://github.com/acidanthera/OpenCorePkg/blob/master/Docs/AcpiSamples/SSDT-RTC0.dsl
//
// Uses the CORP name to denote where this was created for troubleshooting purposes.
//
DefinitionBlock ("", "SSDT", 2, "CORP", "RTCAWAC", 0x00000000)
{
"""
        if any((x.get("has_var") for x in (awac_dict,rtc_dict))):
            ssdt += """    External (STAS, IntObj)
    Scope (\)
    {
        Method (_INI, 0, NotSerialized)  // _INI: Initialize
        {
            If (_OSI ("Darwin"))
            {
                STAS = One
            }
        }
    }
"""
        for x in (awac_dict,rtc_dict):
            if not x.get("valid") or x.get("has_var") or not x.get("device"): continue
            # Device was found, and it doesn't have the STAS var - check if we
            # have an _STA (which would be renamed)
            macos,original = ("Zero","0x0F") if x.get("dev_hid") == "ACPI000E" else ("0x0F","Zero")
            if x.get("sta"):
                ssdt += """    External ([[DevPath]], DeviceObj)
    External ([[DevPath]].XSTA, [[sta_type]])
    Scope ([[DevPath]])
    {
        Name (ZSTA, [[Original]])
        Method (_STA, 0, NotSerialized)  // _STA: Status
        {
            If (_OSI ("Darwin"))
            {
                Return ([[macOS]])
            }
            // Default to [[Original]] - but return the result of the renamed XSTA if possible
            If ((CondRefOf ([[DevPath]].XSTA)))
            {
                Store ([[DevPath]].XSTA[[called]], ZSTA)
            }
            Return (ZSTA)
        }
    }
""".replace("[[DevPath]]",x["device"][0]).replace("[[Original]]",original).replace("[[macOS]]",macos).replace("[[sta_type]]",x["sta_type"]).replace("[[called]]"," ()" if x["sta_type"]=="MethodObj" else "")
            elif x.get("dev_hid") == "ACPI000E":
                # AWAC device with no STAS, and no _STA - let's just add one
                ssdt += """    External ([[DevPath]], DeviceObj)
    Scope ([[DevPath]])
    {
        Method (_STA, 0, NotSerialized)  // _STA: Status
        {
            If (_OSI ("Darwin"))
            {
                Return (Zero)
            }
            Else
            {
                Return (0x0F)
            }
        }
    }
""".replace("[[DevPath]]",x["device"][0])
        # Check if we need to setup an RTC range correction
        if rtc_range_needed and rtc_crs_type and crs_lines and rtc_dict.get("valid"):
            ssdt += """    External ([[DevPath]], DeviceObj)
    External ([[DevPath]].XCRS, [[type]])
    Scope ([[DevPath]])
    {
        If (_OSI ("Darwin"))
        {
            // Adjusted _CRS method ripped from DSDT with corrected range
[[NewCRS]]
            // End of adjusted _CRS method
        }
        ElseIf ((CondRefOf ([[DevPath]].XCRS)))
        {
            // Create a new _CRS method that returns the result of the renamed XCRS
            Method (_CRS, 0, Serialized)  // _CRS: Current Resource Settings
            {
                Return ([[DevPath]].XCRS[[method]])
            }
        }
    }
""".replace("[[DevPath]]",rtc_dict["device"][0]) \
    .replace("[[type]]",rtc_crs_type) \
    .replace("[[method]]"," ()" if rtc_crs_type == "Method" else "") \
    .replace("[[NewCRS]]","\n".join([(" "*12)+x for x in crs_lines]))
        # Check if we do not have an RTC device at all
        if not rtc_dict.get("valid") and lpc_name:
            ssdt += """    External ([[LPCName]], DeviceObj)    // (from opcode)
    Scope ([[LPCName]])
    {
        Device (RTC0)
        {
            Name (_HID, EisaId ("PNP0B00"))  // _HID: Hardware ID
            Name (_CRS, ResourceTemplate ()  // _CRS: Current Resource Settings
            {
                IO (Decode16,
                    0x0070,             // Range Minimum
                    0x0070,             // Range Maximum
                    0x01,               // Alignment
                    0x08,               // Length
                    )
                IRQNoFlags ()
                    {8}
            })
            Method (_STA, 0, NotSerialized)  // _STA: Status
            {
                If (_OSI ("Darwin")) {
                    Return (0x0F)
                } Else {
                    Return (0);
                }
            }
        }
    }
""".replace("[[LPCName]]",lpc_name)
        ssdt += "}"
        self.write_ssdt("SSDT-RTCAWAC",ssdt)
        print("")
        print("Done.")
        # See if we just generated a failsafe - and encourage manual checking
        # Would require only an RTC device (no AWAC) that has an _STA with no STAS var
        if rtc_dict.get("valid") and not awac_dict.get("valid") and rtc_dict.get("sta") and not rtc_dict.get("has_var") and not rtc_range_needed:
            print("\n   \u001b[43;1m!! NOTE !!\u001b[0m  Only RTC (no AWAC) detected with an _STA method and no STAS")
            print("               variable! Patch(es) and SSDT-RTCAWAC created as a failsafe,")
            print("               but verify you need them by checking the RTC._STA conditions!")
        self.patch_warn()
        self.u.grab("Press [enter] to return...")

    def get_unique_device(self, path, base_name, starting_number=0, used_names = []):
        # Appends a hex number until a unique device is found
        while True:
            hex_num = hex(starting_number).replace("0x","").upper()
            name = base_name[:-1*len(hex_num)]+hex_num
            if not len(self.d.get_device_paths("."+name)) and not name in used_names:
                return (name,starting_number)
            starting_number += 1

    def ssdt_rhub(self):
        if not self.ensure_dsdt():
            return
        self.u.head("USB Reset")
        print("")
        print("Gathering RHUB/HUBN/URTH devices...")
        rhubs = self.d.get_device_paths("RHUB")
        rhubs.extend(self.d.get_device_paths("HUBN"))
        rhubs.extend(self.d.get_device_paths("URTH"))
        if not len(rhubs):
            print(" - None found!  Aborting...")
            print("")
            self.u.grab("Press [enter] to return to main menu...")
            return
        print(" - Found {:,}".format(len(rhubs)))
        # Gather some info
        patches = []
        tasks = []
        used_names = []
        xhc_num = 2
        ehc_num = 1
        for x in rhubs:
            task = {"device":x[0]}
            print(" --> {}".format(".".join(x[0].split(".")[:-1])))
            name = x[0].split(".")[-2]
            if name in self.illegal_names or name in used_names:
                print(" ----> Needs rename!")
                # Get the new name, and the path to the device and its parent
                task["device"] = ".".join(task["device"].split(".")[:-1])
                task["parent"] = ".".join(task["device"].split(".")[:-1])
                if name.startswith("EHC"):
                    task["rename"],ehc_num = self.get_unique_device(task["parent"],"EH01",ehc_num,used_names)
                    ehc_num += 1 # Increment the name number
                else:
                    task["rename"],xhc_num = self.get_unique_device(task["parent"],"XHCI",xhc_num,used_names)
                    xhc_num += 1 # Increment the name number
                used_names.append(task["rename"])
            else:
                used_names.append(name)
            sta_method = self.d.get_method_paths(task["device"]+"._STA")
            # Let's find out of we need a unique patch for _STA -> XSTA
            if len(sta_method):
                print(" ----> Generating _STA to XSTA patch")
                sta_index = self.d.find_next_hex(sta_method[0][1])[1]
                print(" ------> Found at index {}".format(sta_index))
                sta_hex  = "5F535441"
                xsta_hex = "58535441"
                padl,padr = self.d.get_shortest_unique_pad(sta_hex, sta_index)
                patches.append({"Comment":"{} _STA to XSTA Rename".format(task["device"].split(".")[-1]),"Find":padl+sta_hex+padr,"Replace":padl+xsta_hex+padr})
            # Let's try to get the _ADR
            scope_adr = self.d.get_name_paths(task["device"]+"._ADR")
            task["address"] = self.d.dsdt_lines[scope_adr[0][1]].strip() if len(scope_adr) else "Name (_ADR, Zero)  // _ADR: Address"
            tasks.append(task)
        oc = {"Comment":"SSDT to disable USB RHUB/HUBN/URTH and rename devices","Enabled":True,"Path":"SSDT-USB-Reset.aml"}
        self.make_plist(oc, "SSDT-USB-Reset.aml", patches)
        ssdt = """//
// SSDT to disable RHUB/HUBN/URTH devices and rename PXSX, XHC1, EHC1, and EHC2 devices
//
DefinitionBlock ("", "SSDT", 2, "CORP", "UsbReset", 0x00001000)
{
"""
        # Iterate the USB controllers and add external references
        # Gather the parents first - ensure they're unique, and put them in order
        parents = sorted(list(set([x["parent"] for x in tasks if x.get("parent",None)])))
        for x in parents:
            ssdt += "    External ({}, DeviceObj)\n".format(x)
        for x in tasks:
            ssdt += "    External ({}, DeviceObj)\n".format(x["device"])
        # Let's walk them again and disable RHUBs and rename
        for x in tasks:
            if x.get("rename",None):
                # Disable the old controller
                ssdt += """
    Scope ([[device]])
    {
        Method (_STA, 0, NotSerialized)  // _STA: Status
        {
            If (_OSI ("Darwin"))
            {
                Return (Zero)
            }
            Else
            {
                Return (0x0F)
            }
        }
    }

    Scope ([[parent]])
    {
        Device ([[new_device]])
        {
            [[address]]
            Method (_STA, 0, NotSerialized)  // _STA: Status
            {
                If (_OSI ("Darwin"))
                {
                    Return (0x0F)
                }
                Else
                {
                    Return (Zero)
                }
            }
        }
    }
""".replace("[[device]]",x["device"]).replace("[[parent]]",x["parent"]).replace("[[address]]",x.get("address","Name (_ADR, Zero)  // _ADR: Address")).replace("[[new_device]]",x["rename"])
            else:
                # Only disabling the RHUB
                ssdt += """
    Scope ([[device]])
    {
        Method (_STA, 0, NotSerialized)  // _STA: Status
        {
            If (_OSI ("Darwin"))
            {
                Return (Zero)
            }
            Else
            {
                Return (0x0F)
            }
        }
    }
    """.replace("[[device]]",x["device"])
        ssdt += "\n}"
        self.write_ssdt("SSDT-USB-Reset",ssdt)
        print("")
        print("Done.")
        self.patch_warn()
        self.u.grab("Press [enter] to return...")
        return

    def ssdt_usbx(self):
        usbx_props = {
            "kUSBSleepPowerSupply":"0x13EC",
            "kUSBSleepPortCurrentLimit":"0x0834",
            "kUSBWakePowerSupply":"0x13EC",
            "kUSBWakePortCurrentLimit":"0x0834"
        }
        while True:
            self.u.head("USBX Device")
            print("")
            print("Current USBX Device Properties To Use:")
            print("")
            if usbx_props:
                for i,x in enumerate(usbx_props,start=1):
                    print("{}. {} -> {}".format(i,x,usbx_props[x]))
            else:
                print(" - No properties set")
            print("")
            print("B. Build SSDT-USBX")
            print("A. Remove All")
            print("M. Return to Menu")
            print("Q. Quit")
            print("")
            print("Remove a property by typing its key or number (ie kUSBSleepPowerSupply)")
            print("Add/Edit a property using this format key:value (ie kUSBWakePowerSupply:0x13EC)")
            print("Values must be a 16-bit hexadecimal integer")
            print("")
            menu = self.u.grab("Please enter your selection (default is B):  ")
            if not menu: menu = "b"
            if menu.lower() == "m": return
            elif menu.lower() == "q": self.u.custom_quit()
            elif menu.lower() == "a": usbx_props = {}
            elif menu.lower() == "b" and usbx_props: break
            elif ":" in menu:
                try:
                    key,value = menu.split(":")
                    if key.isnumeric(): # Assume they want to update a number
                        key = list(usbx_props)[int(key)-1]
                    else: # Assume we're adding a new one - make sure it's just alpha chars
                        key = "".join([x for x in key if x.isalpha()])
                    value = self.hexy(int(value,16),pad_to=4)
                    assert len(value) == 6 # Ensure it's no larger than 16-bits
                    usbx_props[key] = value
                except: pass
            elif menu.isnumeric(): # Assume it's a value to remove
                try:
                    usbx_props.pop(list(usbx_props)[int(menu)-1],None)
                except: pass
            else: # Assume it's a value we're trying to remove
                usbx_props.pop(menu,None)
        # Now build!
        self.u.head("USBX Device")
        print("")
        print("Creating generic SSDT-USBX...")
        oc = {"Comment":"Generic USBX device for USB power properties","Enabled":True,"Path":"SSDT-USBX.aml"}
        self.make_plist(oc, "SSDT-USBX.aml", [])
        ssdt = """// Generic USBX Device with power properties injected
// Edited from:
// https://github.com/dortania/OpenCore-Post-Install/blob/master/extra-files/SSDT-USBX.aml
DefinitionBlock ("", "SSDT", 2, "CORP", "SsdtUsbx", 0x00001000)
{
    Scope (\_SB)
    {
        Device (USBX)
        {
            Name (_ADR, Zero)  // _ADR: Address
            Method (_DSM, 4, NotSerialized)  // _DSM: Device-Specific Method
            {
                If (LEqual (Arg2, Zero)) { Return (Buffer () { 0x03 }) }
                Return (Package ()
                {"""
        for i,key in enumerate(usbx_props,start=1):
            ssdt += "\n                    \"{}\",".format(key)
            ssdt += "\n                    {}".format(usbx_props[key])
            if i < len(usbx_props): ssdt += ","
        ssdt += """
                })
            }
            Method (_STA, 0, NotSerialized)  // _STA: Status
            {
                If (_OSI ("Darwin"))
                {
                    Return (0x0F)
                }
                Else
                {
                    Return (Zero)
                }
            }
        }
    }
}"""
        self.write_ssdt("SSDT-USBX",ssdt)
        print("")
        print("Done.")
        self.patch_warn()
        self.u.grab("Press [enter] to return...")
        return

    def ssdt_xosi(self):
        if not self.ensure_dsdt():
            return
        # Let's see what, if any, the highest version contained in the DSDT is
        highest_osi = None
        for x in self.osi_strings:
            if self.osi_strings[x] in self.d.dsdt:
                highest_osi = x
        while True:
            lines = [""]
            pad = len(str(len(self.osi_strings)))
            for i,x in enumerate(self.osi_strings,start=1):
                lines.append("{}. {} ({})".format(str(i).rjust(pad),x,self.osi_strings[x]))
            if highest_osi:
                lines.append("")
                lines.append("A. Auto-Detected ({} - {})".format(highest_osi,self.osi_strings[highest_osi]))
            lines.append("")
            lines.append("M. Main")
            lines.append("Q. Quit")
            lines.append("")
            self.u.resize(self.w, max(len(lines)+4,self.h))
            self.u.head("XOSI")
            print("\n".join(lines))
            menu = self.u.grab("Please select the latest Windows version for SSDT-XOSI{}:  ".format(
                " (default is A)" if highest_osi else ""
            ))
            if not len(menu): menu = "a" # Use the default if we passed nothing
            if menu.lower() == "m": return
            if menu.lower() == "q":
                self.u.resize(self.w,self.h)
                self.u.custom_quit()
            if menu.lower() == "a" and highest_osi:
                target_string = highest_osi
                break
            # Make sure we got a number - and it's within our range
            try:
                target_string = list(self.osi_strings)[int(menu)-1]
            except:
                continue
            # Got a valid option - break out and create the SSDT
            break
        self.u.resize(self.w,self.h)
        self.u.head("XOSI")
        print("")
        print("Creating SSDT-XOSI with support through {}...".format(target_string))
        ssdt = """DefinitionBlock ("", "SSDT", 2, "DRTNIA", "XOSI", 0x00001000)
{
    Method (XOSI, 1, NotSerialized)
    {
        // Edited from:
        // https://github.com/dortania/Getting-Started-With-ACPI/blob/master/extra-files/decompiled/SSDT-XOSI.dsl
        // Based off of: 
        // https://docs.microsoft.com/en-us/windows-hardware/drivers/acpi/winacpi-osi#_osi-strings-for-windows-operating-systems
        // Add OSes from the below list as needed, most only check up to Windows 2015
        // but check what your DSDT looks for
        Local0 = Package ()
            {
"""
        # Iterate our OS versions, and stop once we've added the last supported
        for i,x in enumerate(self.osi_strings,start=1):
            osi_string = self.osi_strings[x]
            ssdt += "                \"{}\"".format(osi_string)
            if x == target_string or i==len(self.osi_strings): # Last one - bail
                ssdt += " // "+x
                break
            ssdt += ", // "+x+"\n" # Add a comma and newline for the next value
        ssdt +="""\n            }
        If (_OSI ("Darwin")) { Return ((Ones != Match (Local0, MEQ, Arg0, MTR, Zero, Zero))) }
        Else { Return (_OSI (Arg0)) }
    }
}"""
        patches = []
        print("Checking for OSID Method...")
        osid = self.d.get_method_paths("OSID")
        if osid:
            print(" - Located {} Method at offset {}".format(osid[0][0],osid[0][1]))
            print(" - Creating OSID to XSID rename...")
            patches.append({"Comment":"OSID to XSID rename - must come before _OSI to XOSI rename!","Find":"4F534944","Replace":"58534944"})
        else:
            print(" - Not found, no OSID to XSID rename needed")
        print("Creating _OSI to XOSI rename...")
        patches.append({"Comment":"_OSI to XOSI rename - requires SSDT-XOSI.aml","Find":"5F4F5349","Replace":"584F5349"})
        self.write_ssdt("SSDT-XOSI",ssdt)
        oc = {"Comment":"_OSI override to return true through {} - requires _OSI to XOSI rename".format(target_string),"Enabled":True,"Path":"SSDT-XOSI.aml"}
        self.make_plist(oc, "SSDT-XOSI.aml", patches, replace=True)
        print("")
        print("Done.")
        self.patch_warn()
        self.u.grab("Press [enter] to return...")
        return

    def get_address_from_line(self, line, split_by="_ADR, "):
        try:
            return int(self.d.dsdt_lines[line].split(split_by)[1].split(")")[0].replace("Zero","0x0").replace("One","0x1"),16)
        except:
            return None

    def hexy(self,integer,pad_to=0):
        return "0x"+hex(integer)[2:].upper().rjust(pad_to,"0")

    def get_bridge_devices(self, path):
        # Takes a Pci(x,x)/Pci(x,x) style path, and returns named bridges and addresses
        adrs = re.split(r"#|\/",path.lower().replace("pciroot(","").replace("pci(","").replace(")",""))
        # Walk the addresses and create our bridge objects
        bridges = []
        for bridge in adrs:
            if not len(bridge): continue # Skip empty entries
            if not "," in bridge: return # Uh... we don't want to bridge the PciRoot - something's wrong.
            try:
                adr1,adr2 = [int(x,16) for x in bridge.split(",")]
                # Join the addresses as a 32-bit int
                adr_int = (adr1 << 16) + adr2
                adr = {0:"Zero",1:"One"}.get(adr_int,"0x"+hex(adr_int).upper()[2:].rjust(8 if adr1 > 0 else 0,"0"))
                brg_num = str(hex(len(bridges))[2:].upper())
                name = "BRG0"[:-len(brg_num)]+brg_num
                bridges.append((name,adr))
            except:
                return [] # Failed :(
        return bridges

    def sanitize_device_path(self, device_path):
        # Walk the device_path, gather the addresses, and rebuild it
        if not device_path.lower().startswith("pciroot("):
            # Not a device path - bail
            return
        # Strip out PciRoot() and Pci() - then split by separators
        adrs = re.split(r"#|\/",device_path.lower().replace("pciroot(","").replace("pci(","").replace(")",""))
        new_path = []
        for i,adr in enumerate(adrs):
            if i == 0:
                # Check for roots
                if "," in adr: return # Broken
                try: new_path.append("PciRoot({})".format(self.hexy(int(adr,16))))
                except: return # Broken again :(
            else:
                if "," in adr: # Not Windows formatted
                    try: adr1,adr2 = [int(x,16) for x in adr.split(",")]
                    except: return # REEEEEEEEEE
                else:
                    try:
                        adr = int(adr,16)
                        adr2,adr1 = adr & 0xFF, adr >> 8 & 0xFF
                    except: return # AAAUUUGGGHHHHHHHH
                # Should have adr1 and adr2 - let's add them
                new_path.append("Pci({},{})".format(self.hexy(adr1),self.hexy(adr2)))
        return "/".join(new_path)

    def get_longest_match(self, device_dict, match_path, adj=False):
        matches = self.get_all_matches(device_dict,match_path,adj=adj)
        if not matches: return
        return sorted(matches,key=lambda x:x[-1],reverse=True)[0]

    def get_all_matches(self, device_dict, match_path, adj=False):
        matched = None
        exact   = False
        key     = "adj_path" if adj else "path"
        matches = []
        for d in device_dict:
            device = device_dict[d].get(key)
            if not device: continue
            if match_path.lower().startswith(device.lower()):
                matches.append((d,device_dict[d],device.lower()==match_path.lower(),len(device)))
        return matches

    def get_device_path(self):
        while True:
            self.u.head("Input Device Path")
            print("")
            print("A valid device path will have one of the following formats:")
            print("")
            print("macOS:   PciRoot(0x0)/Pci(0x0,0x0)/Pci(0x0,0x0)")
            print("Windows: PCIROOT(0)#PCI(0000)#PCI(0000)")
            print("")
            print("M. Main")
            print("Q. Quit")
            print(" ")
            path = self.u.grab("Please enter the device path needing bridges:\n\n")
            if path.lower() == "m":
                return
            if path.lower() == "q":
                self.u.custom_quit()
            path = self.sanitize_device_path(path)
            if not path: continue
            return path

    def pci_bridge(self):
        if not self.ensure_dsdt(): return
        test_path = self.get_device_path()
        if not test_path: return
        self.u.head("Building Bridges")
        print("")
        print("Gathering ACPI devices...")
        # Let's gather our roots - and any other paths that and in _ADR
        pci_roots = self.d.get_device_paths_with_hid(hid="PNP0A08")
        pci_roots += self.d.get_device_paths_with_hid(hid="PNP0A03")
        pci_roots += self.d.get_device_paths_with_hid(hid="ACPI0016")
        paths = self.d.get_path_of_type(obj_type="Name",obj="_ADR")
        # Let's create our dictionary device paths - starting with the roots
        print("Generating device paths...")
        device_dict = {}
        pci_root_paths = []
        for path in pci_roots:
            if path[0] in device_dict: continue # Already have it
            device_uid = self.d.get_name_paths(obj=path[0]+"._UID")
            if device_uid and len(device_uid)==1:
                adr = self.get_address_from_line(device_uid[0][1],split_by="_UID, ")
            else: # Assume 0
                adr = 0
            device_dict[path[0]] = {"path":"PciRoot({})".format(self.hexy(adr))}
            pci_root_paths.append(device_dict[path[0]])
        # First - let's create a new list of tuples with the ._ADR stripped
        # The goal here is to ensure pathing is listed in the proper order.
        sanitized_paths = sorted([(x[0][0:-5],x[1],x[2]) for x in paths])
        for path in sanitized_paths:
            adr = self.get_address_from_line(path[1])
            adr_overflow = False
            # Let's bitshift to get both addresses
            try:
                adr1,adr2 = adr >> 16 & 0xFFFF, adr & 0xFFFF
                radr1,radr2 = adr1,adr2 # Save placeholders in case we overflow
                if adr1 > 0xFF: # Overflowed
                    adr_overflow = True
                    radr1 = 0
                if adr2 > 0xFF: # Overflowed
                    adr_overflow = True
                    radr2 = 0
            except:
                continue # Bad address?
            # Let's check if our path already exists
            if path[0] in device_dict: continue # Skip
            # Doesn't exist - let's see if the parent path does?
            parent = ".".join(path[0].split(".")[:-1])
            parent_device = device_dict.get(parent)
            if not parent_device or not parent_device.get("path"): continue # No parent either - bail...
            # Our parent path exists - let's copy its device_path, and append our addressing
            device_path = parent_device["path"]
            device_path += "/Pci({},{})".format(self.hexy(adr1),self.hexy(adr2))
            device_dict[path[0]] = {"path":device_path}
            # Check if either we, or our parent has an adr overflow
            if adr_overflow or parent_device.get("adr_overflow"):
                device_dict[path[0]]["adr_overflow"] = True
                parent_path = parent_device.get("adj_path",parent_device["path"])
                device_dict[path[0]]["adj_path"] = parent_path + "/Pci({},{})".format(self.hexy(radr1),self.hexy(radr2))
                if adr_overflow: # It was us, not a parent
                    dev_overflow = device_dict[path[0]].get("dev_overflow",[])
                    dev_overflow.append(path[0])
                    device_dict[path[0]]["dev_overflow"] = dev_overflow
        print("Matching against {}".format(test_path))
        match = self.get_longest_match(device_dict,test_path)
        if not match:
            if pci_root_paths:
                print(" - No matches found!  Your device path must at least start with one")
                print("   of the following PciRoot() options to match the passed DSDT:")
                for p in pci_root_paths:
                    print("   --> {}".format(p))
            else:
                print(" - No matches found!  Please re-check your device path.")
            print("")
            self.u.grab("Press [enter] to return...")
            return
        # We got a match
        print("Matched {} - {}".format(match[0],match[1]["path"]))
        # Check for the longest adj_path as well
        adj_match = self.get_all_matches(device_dict,test_path,adj=True)
        if adj_match:
            print("\nThere are _ADR overflows in the device path!")
            # Get a list of devices to _STA = Zero
            devices = []
            for m in adj_match:
                if not "dev_overflow" in m[1]: continue
                devices.extend([x for x in m[1]["dev_overflow"] if not x in devices])
            if devices:
                print(" - The following devices need to be adjusted for Bridging to work:")
                for d in devices:
                    print(" --> {}".format(d))
                # Walk the paths and generate _STA returns to disable devices
                print(" - Generating _STA renames as needed...")
                patches = []
                ssdt = """
DefinitionBlock ("", "SSDT", 2, "CORP", "ADROVER", 0x00000000)
{
    /*
     * Start copying here if you're adding this info to an existing SSDT-ADROVER!
     */"""
                for d in devices:
                    sta_check = self.get_sta_var(var=None,device=d,dev_name=d.split(".")[-1])
                    if not sta_check["valid"]: continue # Borked - skip
                    patches.extend(sta_check.get("patches",[]))
                    if not sta_check["sta"]: # No _STA method, override it
                        ssdt += """

    External ([[device]], DeviceObj)

    Scope ([[device]])
    {
        Method (_STA, 0, NotSerialized)  // _STA: Status
        {
            If (_OSI ("Darwin"))
            {
                Return (Zero)
            }
            Else
            {
                Return (0x0F)
            }
        }
    }""".replace("[[device]]",d)
                    else: # Got an _STA method
                        ssdt += """

    External ([[device]], DeviceObj)
    External ([[device]].XSTA, [[sta_type]])

    Scope ([[device]])
    {
        Name (ZSTA, 0x0F)
        Method (_STA, 0, NotSerialized)  // _STA: Status
        {
            If (_OSI ("Darwin"))
            {
                Return (Zero)
            }
            // Default to 0x0F - but return the result of the renamed XSTA if possible
            If ((CondRefOf ([[device]].XSTA)))
            {
                Store ([[device]].XSTA[[called]], ZSTA)
            }
            Return (ZSTA)
        }
    }""".replace("[[device]]",d).replace("[[sta_type]]",sta_check["sta_type"]).replace("[[called]]"," ()" if sta_check["sta_type"]=="MethodObj" else "")
                ssdt += """
    /*
     * End copying here if you're adding this info to an existing SSDT-ADROVER!
     */
}"""
                # Save the SSDT and generate any patches
                print("Generating SSDT-ADROVER...")
                self.write_ssdt("SSDT-ADROVER",ssdt)
                oc = {"Comment":"Disables devices with _ADR overflow for bridging","Enabled":True,"Path":"SSDT-ADROVER.aml"}
                self.make_plist(oc,"SSDT-ADROVER.aml",patches)
                print("\n\u001b[41;1m!! WARNING !!\u001b[0m SSDT-ADROVER disables existing devices - VERIFY BEFORE USING!!\n")
            else:
                print(" - Devices need to be adjusted for Bridging to work!")
        if match[2]:
            print(" - No bridge needed!")
            if adj_match: self.patch_warn()
            else: print("")
            self.u.grab("Press [enter] to return...")
            return
        remain = test_path[match[-1]+1:]
        print("Generating bridge{} for {}...".format(
            "" if not remain.count("/") else "s",
            remain
        ))
        bridges = self.get_bridge_devices(remain)
        if not bridges:
            print(" - Something went wrong!")
            print("")
            self.u.grab("Press [enter] to return...")
            return
        print("Generating SSDT-Bridge...")

        ssdt = """// Source and info from:
// https://github.com/acidanthera/OpenCorePkg/blob/master/Docs/AcpiSamples/Source/SSDT-BRG0.dsl
DefinitionBlock ("", "SSDT", 2, "CORP", "PCIBRG", 0x00000000)
{
    /*
     * Start copying here if you're adding this info to an existing SSDT-Bridge!
     */
    External ([[scope]], DeviceObj)
    Scope ([[scope]])
    {
""".replace("[[scope]]",match[0])
        ssdt_end = """    }
    /*
     * End copying here if you're adding this info to an existing SSDT-Bridge!
     */
}
"""
        # Let's iterate our bridges
        pc = "    " # Pad char
        for i,bridge in enumerate(bridges,start=2):
            if i-1==len(bridges):
                ssdt += pc*i + "// Customize this device name if needed, eg. GFX0\n"
                ssdt += pc*i + "Device (PXSX)\n"
            else:
                ssdt += pc*i + "Device ({})\n".format(bridge[0])
            ssdt += pc*i + "{\n"
            if i-1==len(bridges):
                ssdt += pc*(i+1) + "// Target Device Path:\n"
                ssdt += pc*(i+1) + "// {}\n".format(test_path)
            ssdt += pc*(i+1) + "Name (_ADR, {})\n".format(bridge[1])
            ssdt_end = pc*i + "}\n" + ssdt_end
        ssdt += ssdt_end
        self.write_ssdt("SSDT-Bridge",ssdt)
        oc = {"Comment":"Defines missing PCI bridges for property injection","Enabled":True,"Path":"SSDT-Bridge.aml"}
        self.make_plist(oc, "SSDT-Bridge.aml", ())
        print("")
        print("Done.")
        self.patch_warn()
        self.u.grab("Press [enter] to return...")
        return

    def ssdt_pnlf(self):
        if not self.ensure_dsdt(): return
        self.u.head("Generating PNLF")
        print("")
        print("Gathering ACPI devices...")
        # Let's our device _ADR entries, and find the iGPU - which
        # is *always* at 0x00020000 on Intel machines.
        # Some do not have them defined in the DSDT though - so we'll
        # also search for common names (GFX0, IGPU, VID, VID0, VID1)
        # under the PCI roots as well.
        igpu = None
        guessed = False
        paths = self.d.get_path_of_type(obj_type="Name",obj="_ADR")
        print("Looking for iGPU device at 0x00020000...")
        for path in paths:
            adr = self.get_address_from_line(path[1])
            if adr == 0x00020000:
                igpu = path[0][:-5]
                print(" - Found at {}".format(igpu))
                break
        if not igpu: # Try matching by name
            print(" - Not found!")
            print("Searching common iGPU names...")
            pci_roots = self.d.get_device_paths_with_hid(hid="PNP0A08")
            pci_roots += self.d.get_device_paths_with_hid(hid="PNP0A03")
            pci_roots += self.d.get_device_paths_with_hid(hid="ACPI0016")
            external = []
            for line in self.d.dsdt_lines:
                if not line.strip().startswith("External ("): continue # We don't need it
                try:
                    path = line.split("(")[1].split(", ")[0]
                    # Prepend the backslash and ensure trailing underscores are stripped.
                    path = "\\"+".".join([x.rstrip("_").replace("\\","") for x in path.split(".")])
                    external.append(path)
                except: pass
            for root in pci_roots:
                for name in ("IGPU","_VID","VID0","VID1","GFX0","VGA","_VGA"):
                    test_path = "{}.{}".format(root[0],name)
                    device = self.d.get_device_paths(test_path)
                    if device: device = device[0][0] # Unpack to the path
                    else:
                        # Walk the external paths and see if it's declared elsewhere?
                        # We're not patching anything directly - just getting a pathing
                        # reference, so it's fine to not have the surrounding code.
                        device = next((x for x in external if test_path == x),None)
                    if not device: continue # Not found :(
                    # Got a device - see if it has an _ADR, and skip if so - as it was wrong in the prior loop
                    if self.d.get_path_of_type(obj_type="Name",obj=device+"._ADR"): continue
                    # At this point - we got a hit
                    igpu = device
                    print(" - Found likely iGPU device at {}".format(igpu))
        if not igpu:
            guessed = True
            print(" - Could not locate an iGPU device!")
            igpu = (pci_roots[0][0] if pci_roots else "\\_SB.PCI0")+".GFX0"
            print(" - Falling back on {}".format(igpu))
        # Now we need to get our _UID
        while True:
            self.u.head("Select _UID for PNLF")
            print("")
            print("_UID |     Supported Platform(s)       | PWMMax")
            print("-----------------------------------------------")
            print(" 14  | Arrandale, Sandy/Ivy Bridge     | 0x0710")
            print(" 15  | Haswell/Broadwell               | 0x0AD9")
            print(" 16  | Skylake/Kaby Lake, some Haswell | 0x056C")
            print(" 17  | Custom LMAX                     | 0x07A1")
            print(" 18  | Custom LMAX                     | 0x1499")
            print(" 19  | CoffeeLake and newer            | 0xFFFF")
            print(" 99  | Other (requires custom applbkl-name/applbkl-data dev props)")
            print("")
            print("The _UID tells WhateverGreen what backlight data to use.")
            print("More info can be found in WEG's kern_weg.cpp here under appleBacklightData")
            print("")
            print("M. Main Menu")
            print("Q. Quit")
            print("")
            menu = self.u.grab("Please select the target _UID value:  ")
            if menu.lower() == "m": return
            elif menu.lower() == "q": self.u.custom_quit()
            try: uid = int(menu)
            except: continue
            if not uid in (14,15,16,17,18,19):
                while True:
                    self.u.head("Custom _UID for PNLF")
                    print("")
                    print("{} is a custom _UID which may require customization to setup,".format(uid))
                    print("or not have support at all.")
                    print("")
                    menu = self.u.grab("Are you sure you want to use it? (y/n):  ")
                    if not menu.lower() in ("y","n"): continue
                    break
                if menu.lower() == "n": continue
            break
        self.u.head("Generating PNLF")
        print("")
        print("Creating SSDT-PNLF...")
        print(" - Path: {}".format(igpu))
        print(" - _UID: {}".format(uid))
        if guessed:
            print("")
            print("!!WARNING!!  THIS PATH WAS GUESSED AND MAY NOT BE CORRECT!")
            print("")
        patches = []
        if "PNLF" in self.d.dsdt:
            print("PNLF detected in DSDT - generating rename...")
            patches.append({"Comment":"PNLF to XNLF Rename","Find":"504E4C46","Replace":"584E4C46"})
        ssdt = """DefinitionBlock ("", "SSDT", 2, "CORP", "PNLF", 0x00000000)
{
    External ([[igpu_path]], DeviceObj)

    Device ([[igpu_path]].PNLF)
    {
        Name (_HID, EisaId ("APP0002"))  // _HID: Hardware ID
        Name (_CID, "backlight")  // _CID: Compatible ID

        // _UID |     Supported Platform(s)       | PWMMax
        // -----------------------------------------------
        //  14  | Arrandale, Sandy/Ivy Bridge     | 0x0710
        //  15  | Haswell/Broadwell               | 0x0AD9
        //  16  | Skylake/Kaby Lake, some Haswell | 0x056C
        //  17  | Custom LMAX                     | 0x07A1
        //  18  | Custom LMAX                     | 0x1499
        //  19  | CoffeeLake and newer            | 0xFFFF
        //  99  | Other (requires custom applbkl-name/applbkl-data dev props)

        Name (_UID, [[uid_value]])  // _UID: Unique ID: [[uid_dec]]
        
        Method (_STA, 0, NotSerialized)  // _STA: Status
        {
            If (_OSI ("Darwin"))
            {
                Return (0x0B)
            }
            Else
            {
                Return (Zero)
            }
        }
    }
}""".replace("[[igpu_path]]",igpu).replace("[[uid_value]]",self.hexy(uid)).replace("[[uid_dec]]",str(uid))
        self.write_ssdt("SSDT-PNLF",ssdt)
        oc = {
            "Comment":"Defines PNLF device with a _UID of {} for backlight control{}".format(
                uid,
                " - requires PNLF to XNLF rename" if patches else ""
            ),
            "Enabled":True,
            "Path":"SSDT-PNLF.aml"
        }
        self.make_plist(oc, "SSDT-PNLF.aml", patches, replace=True)
        print("")
        print("Done.")
        self.patch_warn()
        self.u.grab("Press [enter] to return...")
        return

    def main(self):
        self.u.resize(self.w,self.h)
        cwd = os.getcwd()
        self.u.head()
        print("")
        print("Current DSDT:  {}".format(self.dsdt))
        print("")
        print("1. FixHPET       - Patch Out IRQ Conflicts")
        print("2. FakeEC        - OS-Aware Fake EC")
        print("3. FakeEC Laptop - Only Builds Fake EC - Leaves Existing Untouched")
        print("4. USBX          - Power properties for USB on SKL and newer SMBIOS")
        print("5. PluginType    - Redefines CPU Objects as Processor and sets plugin-type = 1")
        print("6. PMC           - Enables Native NVRAM on True 300-Series Boards")
        print("7. RTCAWAC       - Context-Aware AWAC Disable and RTC Enable/Fake/Range Fix")
        print("8. USB Reset     - Reset USB controllers to allow hardware mapping")
        print("9. PCI Bridge    - Create missing PCI bridges for passed device path")
        print("0. PNLF          - Sets up a PNLF device for laptop backlight control")
        print("A. XOSI          - _OSI rename and patch to return true for a range of Windows")
        print("                   versions - also checks for OSID")
        print("")
        if sys.platform.startswith("linux") or sys.platform == "win32":
            print("P. Dump DSDT     - Automatically dump the system DSDT")
        print("D. Select DSDT or origin folder")
        print("Q. Quit")
        print("")
        menu = self.u.grab("Please make a selection:  ")
        if not len(menu):
            return
        if menu.lower() == "q":
            self.u.custom_quit()
        if menu.lower() == "d":
            self.dsdt = self.select_dsdt()
            return
        if menu == "1":
            self.fix_hpet()
        elif menu == "2":
            self.fake_ec()
        elif menu == "3":
            self.fake_ec(True)
        elif menu == "4":
            self.ssdt_usbx()
        elif menu == "5":
            self.plugin_type()
        elif menu == "6":
            self.ssdt_pmc()
        elif menu == "7":
            self.ssdt_awac()
        elif menu == "8":
            self.ssdt_rhub()
        elif menu == "9":
            self.pci_bridge()
        elif menu == "0":
            self.ssdt_pnlf()
        elif menu.lower() == "a":
            self.ssdt_xosi()
        elif menu.lower() == "p" and (sys.platform.startswith("linux") or sys.platform == "win32"):
            self.dsdt = self.load_dsdt(
                self.d.dump_dsdt(
                    os.path.join(os.path.dirname(os.path.realpath(__file__)),self.output),
                    decompile=False
                )
            )
        return

if __name__ == '__main__':
    if 2/3 == 0: input = raw_input
    s = SSDT()
    while True:
        try:
            s.main()
        except Exception as e:
            print("An error occurred: {}".format(e))
            input("Press [enter] to continue...")
