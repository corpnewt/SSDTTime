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
        self.iasl = None
        self.dsdt = None
        self.scripts = "Scripts"
        self.output = "Results"
        self.legacy_irq = ["TMR","TIMR","IPIC","RTC"] # Could add HPET for extra patch-ness, but shouldn't be needed
        self.target_irqs = [0,8,11]
        self.illegal_names = ("XHC1","EHC1","EHC2","PXSX")

    def select_dsdt(self):
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
        if out:
            if self.d.load(out):
                return out
        return self.select_dsdt()

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
        if sys.platform == "win32":
            iasl_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), self.scripts, "iasl.exe")
        else:
            iasl_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), self.scripts, "iasl")
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
    
    def make_plist(self, oc_acpi, cl_acpi, patches):
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
        oc_plist = self.ensure_path(oc_plist,("ACPI","Add"))
        oc_plist = self.ensure_path(oc_plist,("ACPI","Patch"))
        cl_plist = self.ensure_path(cl_plist,("ACPI","SortedOrder"))
        cl_plist = self.ensure_path(cl_plist,("ACPI","DSDT","Patches"))

        # Add the .aml references
        if any(oc_acpi["Comment"] == x["Comment"] for x in oc_plist["ACPI"]["Add"]):
            print(" -> Add \"{}\" already in OC plist!".format(oc_acpi["Comment"]))
        else:
            oc_plist["ACPI"]["Add"].append(oc_acpi)
        if any(cl_acpi == x for x in cl_plist["ACPI"]["SortedOrder"]):
            print(" -> \"{}\" already in Clover plist!".format(cl_acpi))
        else:
            cl_plist["ACPI"]["SortedOrder"].append(cl_acpi)

        # Iterate the patches
        for p in patches:
            if any(x["Comment"] == p["Comment"] for x in oc_plist["ACPI"]["Patch"]):
                print(" -> Patch \"{}\" already in OC plist!".format(p["Comment"]))
            else:
                print(" -> Adding Patch \"{}\" to OC plist!".format(p["Comment"]))
                oc_plist["ACPI"]["Patch"].append(self.get_oc_patch(p))
            if any(x["Comment"] == p["Comment"] for x in cl_plist["ACPI"]["DSDT"]["Patches"]):
                print(" -> Patch \"{}\" already in Clover plist!".format(p["Comment"]))
            else:
                print(" -> Adding Patch \"{}\" to Clover plist!".format(p["Comment"]))
                cl_plist["ACPI"]["DSDT"]["Patches"].append(self.get_clover_patch(p))         
        # Write the plists
        with open(os.path.join(output,"patches_OC.plist"),"wb") as f:
            plist.dump(oc_plist,f)
        with open(os.path.join(output,"patches_Clover.plist"),"wb") as f:
            plist.dump(cl_plist,f)

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
        print("")
        self.u.grab("Press [enter] to return...")

    def plugin_type(self):
        if not self.ensure_dsdt():
            return
        self.u.head("Plugin Type")
        print("")
        print("Determining CPU name scheme...")
        try: cpu_name = self.d.get_processor_paths("")[0][0]
        except: cpu_name = None
        if not cpu_name:
            print(" - Could not locate Processor object! Aborting!")
            print("")
            self.u.grab("Press [enter] to return to main menu...")
            return
        else:
            print(" - Found {}".format(cpu_name))
        oc = {"Comment":"Plugin Type","Enabled":True,"Path":"SSDT-PLUG.aml"}
        self.make_plist(oc, "SSDT-PLUG.aml", ())
        print("Creating SSDT-PLUG...")
        ssdt = """
//
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
        self.write_ssdt("SSDT-PLUG",ssdt)
        print("")
        print("Done.")
        print("")
        self.u.grab("Press [enter] to return...")

    def list_irqs(self):
        # Walks the DSDT keeping track of the current device and
        # saving the IRQNoFlags if found
        devices = {}
        current_device = None
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
                        devices[current_device] += ":"+num
                    else: # Skipped at least one line
                        irq_index = self.d.find_next_hex(index)[1]
                        devices[current_device] += "-"+str(irq_index)+"|"+num
                else:
                    irq_index = self.d.find_next_hex(index)[1]
                    devices[current_device] = str(irq_index)+"|"+num
                irq = False
                last_irq = True
            elif "Device (" in line:
                current_device = line.split("(")[1].split(")")[0]
                last_irq = False
            elif "IRQNoFlags" in line and current_device:
                # Next line has our interrupts
                irq = True
            # Check if just a filler line
            elif len(line.replace("{","").replace("}","").replace("(","").replace(")","").replace(" ","").split("//")[0]):
                # Reset last IRQ as it's not in a row
                last_irq = False
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
        while True:
            pad = 19
            self.u.head("Select IRQs To Nullify")
            print("")
            print("Current Legacy IRQs:")
            print("")
            if not len(irqs):
                print(" - None Found")
            pad+=len(irqs) if len(irqs) else 1
            for x in irqs:
                print(" - {}: {}".format(x.rjust(4," "),self.get_all_irqs(irqs[x])))
            print("")
            print("C. Only Conflicting IRQs from Legacy Devices ({} from IPIC/TMR/RTC)".format(",".join([str(x) for x in self.target_irqs]) if len(self.target_irqs) else "None"))
            print("O. Only Conflicting IRQs ({})".format(",".join([str(x) for x in self.target_irqs]) if len(self.target_irqs) else "None"))
            print("L. Legacy IRQs (from IPIC, TMR/TIMR, and RTC)")
            print("")
            print("You can also type your own list of Devices and IRQs.")
            print("The format is DEV1:IRQ1,IRQ2 DEV2:IRQ3,IRQ4")
            print("You can omit the IRQ# to remove all from that device (DEV1: DEV2:1,2,3)")
            print("For example, to remove IRQ 0 from RTC, all from IPIC, and 8 and 11 from TMR:\n")
            print("RTC:0 IPIC: TMR:8,11")
            if pad < 24:
                pad = 24
            self.u.resize(80, pad)
            menu = self.u.grab("Please select an option (default is C):  ")
            if not len(menu):
                menu = "c"
            d = {}
            if menu.lower() == "o":
                for x in irqs:
                    d[x] = self.target_irqs
            elif menu.lower() == "l":
                for x in ["IPIC","TMR","TIMR","RTC"]:
                    d[x] = []
            elif menu.lower() == "c":
                for x in ["IPIC","TMR","TIMR","RTC"]:
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
            self.u.resize(80,24)
            return d

    def fix_hpet(self):
        if not self.ensure_dsdt():
            return
        self.u.head("Fix HPET")
        print("")
        print("Locating HPET's _CRS Method...")
        devices = self.d.get_devices("Method (_CRS")
        hpet = self.d.get_method_paths("HPET._CRS")
        hpatch = self.d.get_method_paths("HPET.XCRS")
        if not len(hpet):
            print(" - Could not locate HPET's _CRS! Aborting!")
            if len(hpatch):
                print(" --> Appears to already be named XCRS!")
            print("")
            self.u.grab("Press [enter] to return to main menu...")
            return
        crs_index = self.d.find_next_hex(hpet[0][1])[1]
        print(" - Found at index {}".format(crs_index))
        crs  = "5F435253"
        xcrs = "58435253"
        padl,padr = self.d.get_shortest_unique_pad(crs, crs_index)
        patches = [{"Comment":"HPET _CRS to XCRS Rename","Find":padl+crs+padr,"Replace":padl+xcrs+padr}]
        devs = self.list_irqs()
        target_irqs = self.get_irq_choice(devs)
        self.u.head("Creating IRQ Patches")
        print("")
        print(" - HPET _CRS to XCRS Rename:")
        print("      Find: {}".format(padl+crs+padr))
        print("   Replace: {}".format(padl+xcrs+padr))
        print("")
        print("Checking IRQs...")
        print("")
        # Let's apply patches as we go
        saved_dsdt = self.d.dsdt_raw
        unique_patches  = {}
        generic_patches = []
        for dev in devs:
            if not dev in target_irqs:
                continue
            irq_patches = self.get_hex_from_irqs(devs[dev],target_irqs[dev])
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
                    name = "{} IRQ {} Patch".format(x, p["remd"])
                    if len(unique_patches[x]) > 1:
                        name += " -  {} of {}".format(i+1, len(unique_patches[x]))
                    patches.append({"Comment":name,"Find":p["find"],"Replace":p["repl"]})
                    print(" - {}".format(name))
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
                name = "Generic IRQ Patch {} of {} - {} - {}".format(i+1,len(generic_set),x["remd"],x["orig"])
                patches.append({"Comment":name,"Find":x["find"],"Replace":x["repl"],"Disabled":True,"Enabled":False})
                print(" - {}".format(name))
                print("      Find: {}".format(x["find"]))
                print("   Replace: {}".format(x["repl"]))
                print("")
        # Restore the original DSDT in memory
        self.d.dsdt_raw = saved_dsdt
        print("Locating HPET...")
        hpet = self.d.get_device_paths_with_hid("PNP0103")
        if not hpet:
            print("HPET could not be located.")
            self.u.grab("Press [enter] to return to main menu...")
            return
        name  = hpet[0][0]
        scope = ".".join(name.split(".")[:-1]) 
        oc = {"Comment":"HPET _CRS (Needs _CRS to XCRS Rename)","Enabled":True,"Path":"SSDT-HPET.aml"}
        self.make_plist(oc, "SSDT-HPET.aml", patches)
        print("Creating SSDT-HPET...")
        ssdt = """//
// Supplementary HPET _CRS from Goldfish64
// Requires the HPET's _CRS to XCRS rename
//
DefinitionBlock ("", "SSDT", 2, "CORP", "HPET", 0x00000000)
{
    [[ext]]
    External ([[name]], DeviceObj)    // (from opcode)
    Name ([[name]]._CRS, ResourceTemplate ()  // _CRS: Current Resource Settings
    {
        IRQNoFlags ()
            {0,8,11}
        Memory32Fixed (ReadWrite,
            0xFED00000,         // Address Base
            0x00000400,         // Address Length
            )
    })
}
""".replace("[[ext]]","External ({}, DeviceObj)    // (from opcode)".format(scope) if len(scope) else "").replace("[[name]]",name)
        self.write_ssdt("SSDT-HPET",ssdt)
        print("")
        print("Done.")
        print("")
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
        print("")
        self.u.grab("Press [enter] to return...")

    def ssdt_awac(self):
        if not self.ensure_dsdt():
            return
        self.u.head("SSDT AWAC")
        print("")
        print("Locating ACPI000E (AWAC) devices...")
        awac_list = self.d.get_device_paths_with_hid("ACPI000E")
        if not len(awac_list):
            print(" - Could not locate any ACPI000E devices!  SSDT-AWAC not needed!")
            print("")
            self.u.grab("Press [enter] to return to main menu...")
            return
        awac = awac_list[0]
        root = awac[0].split(".")[0]
        print(" - Found {}".format(awac[0]))
        print(" --> Verifying _STA...")
        sta  = self.d.get_method_paths(awac[0]+"._STA")
        xsta = self.d.get_method_paths(awac[0]+".XSTA")
        has_stas = False
        lpc_name = None
        patches = []
        if not len(sta) and len(xsta):
            print(" --> _STA already renamed to XSTA!  Aborting!")
            print("")
            self.u.grab("Press [enter] to return to main menu...")
            return
        if len(sta):
            scope = "\n".join(self.d.get_scope(sta[0][1],strip_comments=True))
            if "STAS" in scope:
                # We have an STAS var, and should be able to just leverage it
                has_stas = True
                print(" --> Has STAS variable")
            else: print(" --> Does NOT have STAS variable")
        else:
            print(" --> No _STA method found")
        # Let's find out of we need a unique patch for _STA -> XSTA
        if len(sta) and not has_stas:
            print(" --> Generating _STA to XSTA patch")
            sta_index = self.d.find_next_hex(sta[0][1])[1]
            print(" ----> Found at index {}".format(sta_index))
            sta_hex  = "5F535441"
            xsta_hex = "58535441"
            padl,padr = self.d.get_shortest_unique_pad(sta_hex, sta_index)
            patches.append({"Comment":"AWAC _STA to XSTA Rename","Find":padl+sta_hex+padr,"Replace":padl+xsta_hex+padr})
        print("Locating PNP0B00 (RTC) devices...")
        rtc_list  = self.d.get_device_paths_with_hid("PNP0B00")
        rtc_fake = True
        if len(rtc_list):
            rtc_fake = False
            print(" - Found at {}".format(rtc_list[0][0]))
        else: print(" - None found - fake needed!")
        if rtc_fake:
            print("Locating LPC(B)/SBRG...")
            ec_list = self.d.get_device_paths_with_hid("PNP0C09")
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
        # At this point - we need to do the following:
        # 1. Change STAS if needed
        # 2. Setup _STA with _OSI and call XSTA if needed
        # 3. Fake RTC if needed
        oc = {"Comment":"Incompatible AWAC Fix","Enabled":True,"Path":"SSDT-AWAC.aml"}
        self.make_plist(oc, "SSDT-AWAC.aml", patches)
        print("Creating SSDT-AWAC...")
        ssdt = """//
// SSDT-AWAC source from Acidanthera
// Originals found here:
//  - https://github.com/acidanthera/OpenCorePkg/blob/master/Docs/AcpiSamples/SSDT-AWAC.dsl
//  - https://github.com/acidanthera/OpenCorePkg/blob/master/Docs/AcpiSamples/SSDT-RTC0.dsl
//
// Uses the CORP name to denote where this was created for troubleshooting purposes.
//
DefinitionBlock ("", "SSDT", 2, "CORP", "AWAC", 0x00000000)
{
"""
        if has_stas:
            ssdt += """    External (STAS, IntObj)
    Scope ([[Root]])
    {
        Method (_INI, 0, NotSerialized)  // _INI: Initialize
        {
            If (_OSI ("Darwin"))
            {
                STAS = One
            }
        }
    }
""".replace("[[Root]]",root)
        elif len(sta):
            # We have a renamed _STA -> XSTA method - let's leverage it
            ssdt += """    External ([[AWACName]], DeviceObj)
    External ([[AWACName]].XSTA, MethodObj)
    Scope ([[AWACName]])
    {
        Name (ZSTA, 0x0F)
        Method (_STA, 0, NotSerialized)  // _STA: Status
        {
            If (_OSI ("Darwin"))
            {
                Return (Zero)
            }
            // Default to 0x0F - but return the result of the renamed XSTA if possible
            If ((CondRefOf ([[AWACName]].XSTA)))
            {
                Store ([[AWACName]].XSTA(), ZSTA)
            }
            Return (ZSTA)
        }
    }
""".replace("[[AWACName]]",awac[0])
        else:
            # No STAS, and no _STA - let's just add one
            ssdt += """    External ([[AWACName]], DeviceObj)
    Scope ([[AWACName]])
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
""".replace("[[AWACName]]",awac[0])
        if rtc_fake:
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
        self.write_ssdt("SSDT-AWAC",ssdt)
        print("")
        print("Done.")
        print("")
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
        print("")
        self.u.grab("Press [enter] to return...")
        return

    def main(self):
        cwd = os.getcwd()
        self.u.head()
        print("")
        print("Current DSDT:  {}".format(self.dsdt))
        print("")
        print("1. FixHPET       - Patch Out IRQ Conflicts")
        print("2. FakeEC        - OS-Aware Fake EC")
        print("3. FakeEC Laptop - Only Builds Fake EC - Leaves Existing Untouched")
        print("4. PluginType    - Sets plugin-type = 1 on First ProcessorObj")
        print("5. PMC           - Enables Native NVRAM on True 300-Series Boards")
        print("6. AWAC          - Context-Aware AWAC Disable and RTC Fake")
        print("7. USB Reset     - Reset USB controllers to allow hardware mapping")
        if sys.platform.startswith("linux") or sys.platform == "win32":
            print("8. Dump DSDT     - Automatically dump the system DSDT")
        print("")
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
            self.plugin_type()
        elif menu == "5":
            self.ssdt_pmc()
        elif menu == "6":
            self.ssdt_awac()
        elif menu == "7":
            self.ssdt_rhub()
        elif menu == "8" and (sys.platform.startswith("linux") or sys.platform == "win32"):
            self.dsdt = self.d.dump_dsdt(os.path.join(os.path.dirname(os.path.realpath(__file__)), self.output))
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
