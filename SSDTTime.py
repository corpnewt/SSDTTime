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
            self.w = 120
            self.h = 30
        self.iasl = None
        self.dsdt = None
        self.scripts = "Scripts"
        self.output = "Results"
        self.legacy_irq = ["TMR","TIMR","IPIC","RTC"] # Could add HPET for extra patch-ness, but shouldn't be needed
        self.target_irqs = [0,8,11]
        self.illegal_names = ("XHC1","EHC1","EHC2","PXSX")
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
        oc_plist = self.ensure_path(oc_plist,("ACPI","Add"))
        oc_plist = self.ensure_path(oc_plist,("ACPI","Patch"))
        cl_plist = self.ensure_path(cl_plist,("ACPI","SortedOrder"))
        cl_plist = self.ensure_path(cl_plist,("ACPI","DSDT","Patches"))

        # Add the .aml references
        if replace: # Remove any conflicting entries
            oc_plist["ACPI"]["Add"] = [x for x in oc_plist["ACPI"]["Add"] if oc_acpi["Path"] != x["Path"]]
            cl_plist["ACPI"]["SortedOrder"] = [x for x in cl_plist["ACPI"]["SortedOrder"] if cl_acpi != x]
        if any(oc_acpi["Path"] == x["Path"] for x in oc_plist["ACPI"]["Add"]):
            print(" -> Add \"{}\" already in OC plist!".format(oc_acpi["Path"]))
        else:
            oc_plist["ACPI"]["Add"].append(oc_acpi)
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
        # Write the plists
        with open(os.path.join(output,"patches_OC.plist"),"wb") as f:
            plist.dump(oc_plist,f)
        with open(os.path.join(output,"patches_Clover.plist"),"wb") as f:
            plist.dump(cl_plist,f)

    def patch_warn(self):
        # Warn users to ensure they merge the patches_XX.plist contents with their config.plist
        print("\n!!WARNING!!  Make sure you merge the contents of patches_[OC/Clover].plist")
        print("             with your config.plist!\n")

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
        self.patch_warn()
        self.u.grab("Press [enter] to return...")

    def ssdt_cpur(self):
        if not self.ensure_dsdt():
            return
        self.u.head("CPUR")
        print("")
        print("Determining CPU name scheme...")
        # Set cpu_name to None in case the user built SSDT-PLUG in advance
        cpu_name = None
        try: cpu_name = self.d.get_processor_paths("")[0][0]
        except: cpu_name != None
        if cpu_name:
            print(" - Processor object already exists! You don't need SSDT-CPUR!")
            print("")
            self.u.grab("Press [enter] to return to main menu...")
            return
        print(" - Locating ACPI0007 devices...")
        core_list = self.d.get_device_paths_with_hid("ACPI0007")
        core_number = len(core_list) - 1
        print(f" - Found {core_number + 1} cores.")
        first_core = core_list[0][0].split(".")[2]
        if first_core == "CP00":
            core_prefix = "C0"
        else:
            core_prefix = "CP"
        first_core = core_prefix + "00"
        cpur_uid = 1
        first_core_number = 0
        oc = {"Comment":"SSDT-CPUR","Enabled":True,"Path":"SSDT-CPUR.aml"}
        self.make_plist(oc, "SSDT-CPUR.aml", ())
        print("Creating SSDT-CPUR...")
        ssdt = """//
// Based on the sample found at https://github.com/acidanthera/OpenCorePkg/blob/master/Docs/AcpiSamples/Source/SSDT-PLUG-ALT.dsl
// With information from https://www.insanelymac.com/forum/topic/349526-cpu-wrapping-ssdt-cpu-wrap-ssdt-cpur-acpi0007/
//
DefinitionBlock ("", "SSDT", 2, "SSDTTIME", "SSDTCPUR", 0x00000000)
{
    External (_SB_, DeviceObj)
    Scope (\_SB)
    {
        Processor ([[first_core]], 0x00, 0x00000000, 0x06)
        {
            Name (_HID, "ACPI0007" /* Processor Device */)  // _HID: Hardware ID
            Name (_UID, [[cpur_uid]])  // _UID: Unique ID
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
""".replace("[[first_core]]",first_core).replace("[[cpur_uid]]",str(cpur_uid))
        for i in range(core_number):
            if first_core_number == core_number:
                break
            if first_core_number >= 9:
                core = core_prefix + str(first_core_number + 1)
            else:
                core = core_prefix + "0" + str(first_core_number + 1)
            ssdt += """
        Processor ([[core]], 0x00, 0x00000000, 0x06)
        {
            Name (_HID, "ACPI0007" /* Processor Device */)  // _HID: Hardware ID
            Name (_UID, [[cpur_uid]])  // _UID: Unique ID
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
        }""".replace("[[core]]",(core)).replace("[[cpur_uid]]",str(cpur_uid + 1))
            first_core_number += 1
            cpur_uid +=1

        ssdt += """
    }
}"""
        self.write_ssdt("SSDT-CPUR",ssdt)
        print("")
        print("Done.")
        self.patch_warn()
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
            self.u.resize(self.w, max(pad,self.h))
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
            self.u.resize(self.w,self.h)
            return d

    def fix_hpet(self):
        if not self.ensure_dsdt():
            return
        self.u.head("Fix HPET")
        print("")
        print("Locating HPET's _CRS Method...")
        devices = self.d.get_devices("Method (_CRS")
        hpet = self.d.get_method_paths("HPET._CRS")
        if not hpet:
            # Didn't find a _CRS Method - check for Name
            hpet = self.d.get_name_paths("HPET._CRS")
        if not hpet:
            print(" - Could not locate HPET's _CRS! Aborting!")
            # Check for XCRS to see if the rename is already applied
            hpatch = self.d.get_method_paths("HPET.XCRS")
            if not hpatch:
                # Didn't find XCRS Method - check for Name
                hpatch = self.d.get_name_paths("HPET.XCRS")
            if hpatch:
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
                {
                    "kUSBSleepPowerSupply", 
                    0x13EC, 
                    "kUSBSleepPortCurrentLimit", 
                    0x0834, 
                    "kUSBWakePowerSupply", 
                    0x13EC, 
                    "kUSBWakePortCurrentLimit", 
                    0x0834
                })
            }
            Method (_STA, 0, NotSerialized)  // _STA: Status
            {
                If (_OSI ("Darwin")) { Return (0x0F) }
                Else { Return (Zero) }
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
        while True:
            lines = [""]
            pad = len(str(len(self.osi_strings)))
            for i,x in enumerate(self.osi_strings,start=1):
                lines.append("{}. {} ({})".format(str(i).rjust(pad),x,self.osi_strings[x]))
            lines.append("")
            lines.append("M. Main")
            lines.append("Q. Quit")
            lines.append("")
            self.u.resize(self.w, max(len(lines)+4,self.h))
            self.u.head("XOSI")
            print("\n".join(lines))
            menu = self.u.grab("Please select the latest Windows version for SSDT-XOSI:  ")
            if menu.lower() == "m": return
            if menu.lower() == "q": self.u.custom_quit()
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

    def get_address_from_line(self, line):
        try:
            return int(self.d.dsdt_lines[line].split("_ADR, ")[1].split(")")[0].replace("Zero","0x0").replace("One","0x1"),16)
        except:
            return None

    def hexy(self,integer):
        return "0x"+hex(integer)[2:].upper()

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

    def get_longest_match(self, device_dict, match_path):
        longest = 0
        matched = None
        exact   = False
        for device in device_dict:
            if match_path.lower().startswith(device_dict[device].lower()) and len(device_dict[device])>longest:
                # Got a longer match - set it
                matched = device
                longest = len(device_dict[device])
                # Check if it's an exact match, and bail early
                if device_dict[device].lower() == match_path.lower():
                    exact = True
                    break
        return (matched,device_dict[matched],exact,longest)

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
            path = self.u.grab("Please enter the device path needing bridges:  ")
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
        paths = self.d.get_path_of_type(obj_type="Name",obj="_ADR")
        # Let's create our dictionary device paths - starting with the roots
        print("Generating device paths...")
        device_dict = {}
        for path in pci_roots:
            device_adr = self.d.get_name_paths(obj=path[0]+"._ADR")
            if device_adr and len(device_adr)==1:
                adr = self.get_address_from_line(device_adr[0][1])
                device_dict[path[0]] = "PciRoot({})".format(self.hexy(adr))
        # First - let's create a new list of tuples with the ._ADR stripped
        # The goal here is to ensure pathing is listed in the proper order.
        sanitized_paths = sorted([(x[0][0:-5],x[1],x[2]) for x in paths])
        for path in sanitized_paths:
            adr = self.get_address_from_line(path[1])
            # Let's bitshift to get both addresses
            try:
                adr2,adr1 = adr & 0xFFFF, adr >> 16 & 0xFFFF
            except:
                continue # Bad address?
            # Let's check if our path already exists
            if path[0] in device_dict: continue # Skip
            # Doesn't exist - let's see if the parent path does?
            parent = ".".join(path[0].split(".")[:-1])
            if not parent in device_dict: continue # No parent either - bail...
            # Our parent path exists - let's copy its device_path, and append our addressing
            device_path = device_dict[parent]
            if not device_path: continue # Bail - no device_path set
            device_path += "/Pci({},{})".format(self.hexy(adr1),self.hexy(adr2))
            device_dict[path[0]] = device_path
        print("Matching against {}".format(test_path))
        match = self.get_longest_match(device_dict,test_path)
        if not match:
            print(" - No matches found!")
            print("")
            self.u.grab("Press [enter] to return...")
            return
        if match[2]:
            print(" - No bridge needed!")
            print("")
            self.u.grab("Press [enter] to return...")
            return
        # We got a match - and need bridges
        print("Matched {} - {}".format(match[0],match[1]))
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
        print("Generating SSDT...")

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
        ssdt = """DefinitionBlock ("", "SSDT", 2, "CORP", "PNLF", 0x00000000)
{
    External ([[igpu_path]], DeviceObj)

    If (_OSI ("Darwin"))
    {
        Device ([[igpu_path]].PNLF)
        {
            Name (_HID, EisaId ("APP0002"))  // _HID: Hardware ID
            Name (_CID, "backlight")  // _CID: Compatible ID
            Name (_UID, [[uid_value]])  // _UID: Unique ID
            Name (_STA, 0x0B)  // _STA: Status
        }
    }
}""".replace("[[igpu_path]]",igpu).replace("[[uid_value]]",self.hexy(uid))
        self.write_ssdt("SSDT-PNLF",ssdt)
        oc = {"Comment":"Defines PNLF device with a _UID of {} for backlight control".format(uid),"Enabled":True,"Path":"SSDT-PNLF.aml"}
        self.make_plist(oc, "SSDT-PNLF.aml", (), replace=True)
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
        print("5. PluginType    - Sets plugin-type = 1 on First ProcessorObj")
        print("6. PMC           - Enables Native NVRAM on True 300-Series Boards")
        print("7. AWAC          - Context-Aware AWAC Disable and RTC Fake")
        print("8. USB Reset     - Reset USB controllers to allow hardware mapping")
        print("9. PCI Bridge    - Create missing PCI bridges for passed device path")
        print("0. PNLF          - Sets up a PNLF device for laptop backlight control")
        print("A. CPUR          - Replaces Device objects with Processor objects")
        print("B. XOSI          - _OSI rename and patch to return true for a range of Windows")
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
            self.ssdt_cpur()
        elif menu.lower() == "b":
            self.ssdt_xosi()
        elif menu.lower() == "p" and (sys.platform.startswith("linux") or sys.platform == "win32"):
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
