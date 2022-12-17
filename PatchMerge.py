from Scripts import *
import getpass, os, tempfile, shutil, plistlib, sys, binascii, zipfile, re, string

class PatchMerge:
    def __init__(self):
        self.u = utils.Utils("SSDT Time Patch Merge")
        self.w = 80
        self.h = 24
        if os.name == "nt":
            os.system("color") # Allow ASNI color escapes.
            self.w = 120
            self.h = 30
        self.output = os.path.join(os.path.dirname(os.path.realpath(__file__)),"Results")
        self.oc_path = os.path.join(self.output,"patches_OC.plist")
        self.clover_path = os.path.join(self.output,"patches_Clover.plist")
        self.config_path = None
        self.config_type = None

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

    def patch_plist(self):
        self.u.head("Patching Plist")
        print("")
        print("Loading {}...".format(os.path.basename(self.config_path)))
        try:
            config_data = plist.load(open(self.config_path,"rb"))
        except Exception as e:
            print(" - Failed to load! {}".format(e))
            print("")
            self.u.grab("Press [enter] to return...")
            return
        # Recheck the config.plist type
        self.config_type = "OpenCore" if "PlatformInfo" in config_data else "Clover" if "SMBIOS" in config_data else None
        target_path = self.oc_path if self.config_type == "OpenCore" else self.clover_path if self.config_type == "Clover" else None
        if not target_path:
            print("Could not determine plist type!")
            print("")
            self.u.grab("Press [enter] to return...")
            return
        print("Loading {}...".format(os.path.basename(target_path)))
        try:
            target_data = plist.load(open(target_path,"rb"))
        except Exception as e:
            print(" - Failed to load! {}".format(e))
            print("")
            self.u.grab("Press [enter] to return...")
            return
        print("Ensuring paths in {}...".format(os.path.basename(self.config_path)))
        if self.config_type == "OpenCore":
            print(" - ACPI -> Add...")
            config_data = self.ensure_path(config_data,("ACPI","Add"))
            print(" - ACPI -> Patch...")
            config_data = self.ensure_path(config_data,("ACPI","Patch"))
        else:
            print(" - ACPI -> SortedOrder...")
            config_data = self.ensure_path(config_data,("ACPI","SortedOrder"))
            print(" - ACPI -> DSDT -> Patches...")
            config_data = self.ensure_path(config_data,("ACPI","DSDT","Patches"))
        ssdts = target_data.get("ACPI",{}).get("Add",[]) if self.config_type == "OpenCore" else target_data.get("ACPI",{}).get("SortedOrder",[])
        patch = target_data.get("ACPI",{}).get("Patch",[]) if self.config_type == "OpenCore" else target_data.get("ACPI",{}).get("DSDT",{}).get("Patches",[])
        s_orig = config_data["ACPI"]["Add"] if self.config_type == "OpenCore" else config_data["ACPI"]["SortedOrder"]
        p_orig = config_data["ACPI"]["Patch"] if self.config_type == "OpenCore" else config_data["ACPI"]["DSDT"]["Patches"]
        print("")
        if not ssdts:
            print("--- No SSDTs to add - skipping...")
        else:
            print("--- Walking target SSDTs ({:,} total)...".format(len(ssdts)))
            s_rem = []
            for s in ssdts:
                if isinstance(s,dict):
                    print(" - Checking {}...".format(s["Path"]))
                    existing = [x for x in s_orig if x["Path"] == s["Path"]]
                else:
                    print(" - Checking {}...".format(s))
                    existing = [x for x in s_orig if x == s]
                if existing:
                    print(" --> Located {:,} existing to replace...".format(len(existing)))
                    s_rem.extend(existing)
            if s_rem:
                print(" - Removing {:,} existing duplicate{}...".format(len(s_rem),"" if len(s_rem)==1 else "s"))
                for r in s_rem:
                    if r in s_orig: s_orig.remove(r)
            else:
                print(" - No duplicates to remove...")
            print(" - Adding {:,} SSDT{}...".format(len(ssdts),"" if len(ssdts)==1 else "s"))
            s_orig.extend(ssdts)
        print("")
        if not patch:
            print("--- No patches to add - skipping...")
        else:
            print("--- Walking target patches ({:,} total)...".format(len(patch)))
            p_rem = []
            for p in patch:
                print(" - Checking {}...".format(p["Comment"]))
                existing = [x for x in p_orig if x["Find"] == p["Find"] and x["Replace"] == p["Replace"]]
                if existing:
                    print(" --> Located {:,} existing to replace...".format(len(existing)))
                    p_rem.extend(existing)
            # Remove any dupes
            if p_rem:
                print(" - Removing {:,} existing duplicate{}...".format(len(p_rem),"" if len(p_rem)==1 else "s"))
                for r in p_rem:
                    if r in p_orig: p_orig.remove(r)
            else:
                print(" - No duplicates to remove...")
            print(" - Adding {:,} patch{}...".format(len(patch),"" if len(patch)==1 else "es"))
            p_orig.extend(patch)
        print("")
        output_path = os.path.join(self.output,os.path.basename(self.config_path))
        print("Saving to {}...".format(output_path))
        if os.path.isfile(output_path):
            print(" - Exists, removing first...")
            os.remove(output_path)
        try:
            plist.dump(config_data,open(output_path,"wb"))
        except Exception as e:
            print(" - Failed to save! {}".format(e))
            print("")
            self.u.grab("Press [enter] to return...")
            return
        print(" - Saved.")
        print("")
        print("Done.")
        print("")
        self.u.grab("Press [enter] to return...")

    def select_plist(self):
        while True:
            self.u.head("Select Plist")
            print("")
            print("M. Main Menu")
            print("Q. Quit")
            print("")
            path = self.u.grab("Please drag and drop the config.plist here:  ")
            if not path: continue
            if path.lower() == "m": return
            elif path.lower() == "q": self.u.custom_quit()
            test_path = self.u.check_path(path)
            if not test_path or not os.path.isfile(test_path):
                self.u.head("Invalid Path")
                print("")
                print("That path either does not exist, or is not a file.")
                print("")
                self.u.grab("Returning in 5 seconds...",timeout=5)
                continue
            # Got a file - try to load it
            try:
                config_data = plist.load(open(test_path,"rb"))
            except Exception as e:
                self.u.head("Invalid File")
                print("")
                print("That file failed to load:\n\n{}".format(e))
                print("")
                self.u.grab("Returning in 5 seconds...",timeout=5)
                continue
            # Got a valid file
            self.config_path = test_path
            self.config_type = "OpenCore" if "PlatformInfo" in config_data else "Clover" if "SMBIOS" in config_data else None
            return

    def main(self):
        target_path = self.oc_path if self.config_type == "OpenCore" else self.clover_path if self.config_type == "Clover" else None
        self.u.resize(self.w,self.h)
        self.u.head()
        print("")
        print("Current config.plist:  {}".format(self.config_path))
        print("Type of config.plist:  {}".format(self.config_type or "Unknown"))
        print("Patches Plist:         {}{}".format(
            os.path.basename(target_path) if target_path else target_path,
            "" if not target_path or os.path.exists(target_path) else " - MISSING!"
        ))
        print("")
        print("1. Select config.plist")
        if self.config_path and target_path and os.path.exists(target_path):
            print("2. Patch with {}".format(os.path.basename(target_path)))
        print("")
        print("Q. Quit")
        print("")
        menu = self.u.grab("Please make a selection:  ")
        if not len(menu):
            return
        if menu.lower() == "q":
            self.u.custom_quit()
        elif menu == "1":
            self.select_plist()
        elif menu == "2" and self.config_path and target_path:
            self.patch_plist()

if __name__ == '__main__':
    if 2/3 == 0: input = raw_input
    p = PatchMerge()
    while True:
        try:
            p.main()
        except Exception as e:
            print("An error occurred: {}".format(e))
            print("")
            input("Press [enter] to continue...")
