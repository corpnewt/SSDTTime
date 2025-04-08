from Scripts import utils, plist
import argparse, os

class PatchMerge:
    def __init__(self, config=None, results=None, overwrite=False, interactive=True):
        self.u = utils.Utils("Patch Merge")
        self.w = 80
        self.h = 24
        self.red = "\u001b[41;1m"
        self.yel = "\u001b[43;1m"
        self.grn = "\u001b[42;1m"
        self.blu = "\u001b[46;1m"
        self.rst = "\u001b[0m"
        self.copy_as_path = self.u.check_admin() if os.name=="nt" else False
        if 2/3==0:
            # ANSI escapes don't seem to work properly with python 2.x
            self.red = self.yel = self.grn = self.blu = self.rst = ""
        if os.name == "nt":
            if 2/3!=0:
                os.system("color") # Allow ANSI color escapes.
            self.w = 120
            self.h = 30
        self.interactive = interactive
        self.overwrite = overwrite
        self.target_patches = (
            ("OpenCore","patches_OC.plist"),
            ("Clover","patches_Clover.plist")
        )
        self.config_path = config
        self.config_type = None
        self.output = results or self.get_default_results_folder()
        # Expand paths as needed
        if self.config_path:
            self.config_path = os.path.realpath(self.config_path)
            self.config_type,_,_ = self.get_plist_info(self.config_path)
        if self.output:
            self.output = os.path.realpath(self.output)

    def _get_patches_plists(self, path):
        # Append patches_OC/Clover.plist to the path, and return a list
        # with the format:
        # ((oc_path,exists,plist_name),(clover_path,exists,plist_name))
        path_checks = []
        for p_type,name in self.target_patches:
            if path:
                p = os.path.join(path,name)
                isfile = os.path.isfile(p)
            else:
                p = None
                isfile = False
            path_checks.append((
                p,
                isfile,
                name
            ))
        return path_checks

    def get_default_results_folder(self, prompt=False):
        # Let's attempt to locate a Results folder either in the same
        # directory as this script, or in the parent directory.
        # If none is found - we'll have to prompt the user as needed.
        #
        # Try our directory first
        local_path     = os.path.dirname(os.path.realpath(__file__))
        local_results  = os.path.join(local_path,"Results")
        parent_results = os.path.realpath(os.path.join(local_path,"..","Results"))
        potentials     = []
        for path in (local_results,parent_results):
            if os.path.isdir(path):
                # Check if we have the files we need
                o,c = self._get_patches_plists(path)
                if o[1] or c[1]:
                    potentials.append(path)
        if potentials:
            return potentials[0]
        # If we got here - we didn't find anything - check if we need
        # to prompt
        if not prompt:
            # Nope - bail
            return None
        # We're prompting
        return self.select_results_folder()

    def select_results_folder(self):
        while True:
            self.u.head("Select Results Folder")
            print("")
            if self.copy_as_path:
                print("NOTE:  Currently running as admin on Windows - drag and drop may not work.")
                print("       Shift + right-click in Explorer and select 'Copy as path' then paste here instead.")
                print("")
            print("M. Main Menu")
            print("Q. Quit")
            print("")
            print("NOTE:  This is the folder containing the patches_OC.plist and")
            print("       patches_Clover.plist you are trying to merge.  It will also be where")
            print("       the patched config.plist is saved.")
            print("")
            path = self.u.grab("Please drag and drop the Results folder here:  ")
            if not path:
                continue
            if path.lower() == "m":
                return self.output
            elif path.lower() == "q":
                self.u.custom_quit()
            test_path = self.u.check_path(path)
            if os.path.isfile(test_path):
                # Got a file - get the containing folder
                test_path = os.path.dirname(test_path)
            if not test_path:
                self.u.head("Invalid Path")
                print("")
                print("That path either does not exist, or is not a folder.")
                print("")
                self.u.grab("Press [enter] to return...")
                continue
            # Got a folder - check for patches_OC/Clover.plist
            o,c = self._get_patches_plists(test_path)
            if not (o[1] or c[1]):
                # No patches plists in there
                self.u.head("Missing Files")
                print("")
                print("Neither patches_OC.plist nor patches_Clover.plist were found at that path.")
                print("")
                self.u.grab("Press [enter] to return...")
                continue
            # We got what we need - set and return the path
            self.output = test_path
            return self.output

    def get_ascii_print(self, data):
        # Helper to sanitize unprintable characters by replacing them with
        # ? where needed
        unprintables = False
        all_zeroes = True
        ascii_string = ""
        for b in data:
            if not isinstance(b,int):
                try: b = ord(b)
                except: pass
            if b != 0:
                # Not wildcard matching
                all_zeroes = False
            if ord(" ") <= b < ord("~"):
                ascii_string += chr(b)
            else:
                ascii_string += "?"
                unprintables = True
        return (False if all_zeroes else unprintables,ascii_string)

    def check_normalize(self, patch_or_drop, normalize_headers, check_type="Patch"):
        sig = ("OemTableId","TableSignature")
        if normalize_headers:
            # OpenCore - and NormalizeHeaders is enabled.  Check if we have
            # any unprintable ASCII chars in our OemTableId or TableSignature
            # and warn.
            if any(self.get_ascii_print(plist.extract_data(patch_or_drop.get(x,b"\x00")))[0] for x in sig):
                print("\n{}!! WARNING !!{} NormalizeHeaders is {}ENABLED{}, and table ids contain unprintable".format(
                    self.yel,
                    self.rst,
                    self.grn,
                    self.rst
                ))
                print("              characters! {} may not match or apply!\n".format(check_type))
                return True
        else:
            # Not enabled - check for question marks as that may imply characters
            # were sanitized when creating the patches/dropping tables.
            if any(b"\x3F" in plist.extract_data(patch_or_drop.get(x,b"\x00")) for x in sig):
                print("\n{}!! WARNING !!{} NormalizeHeaders is {}DISABLED{}, and table ids contain '?'!".format(
                    self.yel,
                    self.rst,
                    self.red,
                    self.rst
                ))
                print("              {} may not match or apply!\n".format(check_type))
                return True
        return False

    def ensure_path(self, plist_data, path_list, final_type = list):
        if not path_list:
            return plist_data
        if not isinstance(plist_data,dict):
            plist_data = {} # Override it with a dict
        # Set our initial reference, then iterate the
        # path list
        last = plist_data
        for i,path in enumerate(path_list,start=1):
            # Check if our next path var is in last
            if not path in last:
                last[path] = {} if i < len(path_list) else final_type()
            # Make sure it's the correct type if we're at the
            # end of the entries
            if i >= len(path_list) and not isinstance(last[path],final_type):
                # Override it
                last[path] = final_type()
            # Update our reference
            last = last[path]
        return plist_data

    def get_unique_name(self,name,target_folder,name_append=""):
        # Get a new file name in the target folder so we don't override the original
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

    def pause_interactive(self, return_value=None):
        if self.interactive:
            print("")
            self.u.grab("Press [enter] to return...")
        return return_value

    def patch_plist(self):
        # Retain the config name
        if self.interactive:
            self.u.head("Patching Plist")
            print("")
        # Make sure we have a config_path
        if not self.config_path:
            print("No target plist path specified!")
            return self.pause_interactive()
        # Make sure that config_path exists
        if not os.path.isfile(self.config_path):
            print("Could not locate target plist at:")
            print(" - {}".format(self.config_path))
            return self.pause_interactive()
        # Make sure our output var has a value
        if not self.output:
            print("No Results folder path specified!")
            return self.pause_interactive()
        config_name = os.path.basename(self.config_path)
        print("Loading {}...".format(config_name))
        self.config_type,config_data,e = self.get_plist_info(self.config_path)
        if e:
            print(" - Failed to load! {}".format(e))
            return self.pause_interactive()
        # Recheck the config.plist type
        if not self.config_type:
            print("Could not determine plist type!")
            return self.pause_interactive()
        # Ensure our patches plists exist, and break out info
        # into the target_path and target_name as needed
        target_path,_,target_name = self.get_patch_plist_for_type(
            self.output,
            self.config_type
        )
        # This should only show up if output is None/False/empty
        if not target_path:
            print("Could not locate {} in:".format(target_name or "the required patches plist"))
            print(" - {}".format(self.output))
            return self.pause_interactive()
        # Make sure the path actually exists - and is a file
        if not os.path.isfile(target_path):
            print("Could not locate required patches at:")
            print(" - {}".format(target_path))
            return self.pause_interactive()
        # Set up some preliminary variables for reporting later
        errors_found = normalize_headers = False # Default to off
        target_name = os.path.basename(target_path)
        print("Loading {}...".format(target_name))
        # Load the target plist
        _,target_data,e = self.get_plist_info(target_path)
        if e:
            print(" - Failed to load! {}".format(e))
            return self.pause_interactive()
        print("Ensuring paths in {} and {}...".format(config_name,target_name))
        # Make sure all the needed values are there
        if self.config_type == "OpenCore":
            for p in (("ACPI","Add"),("ACPI","Delete"),("ACPI","Patch")):
                print(" - {}...".format(" -> ".join(p)))
                config_data = self.ensure_path(config_data,p)
                target_data = self.ensure_path(target_data,p)
            print(" - ACPI -> Quirks...")
            config_data = self.ensure_path(config_data,("ACPI","Quirks"),final_type=dict)
            normalize_headers = config_data["ACPI"]["Quirks"].get("NormalizeHeaders",False)
            if not isinstance(normalize_headers,(bool)):
                errors_found = True
                print("\n{}!! WARNING !!{} ACPI -> Quirks -> NormalizeHeaders is malformed - assuming False".format(
                    self.yel,
                    self.rst
                ))
                normalize_headers = False
            # Set up our patch sources
            ssdts = target_data["ACPI"]["Add"]
            patch = target_data["ACPI"]["Patch"]
            drops = target_data["ACPI"]["Delete"]
            # Set up our original values
            s_orig = config_data["ACPI"]["Add"]
            p_orig = config_data["ACPI"]["Patch"]
            d_orig = config_data["ACPI"]["Delete"]
        else:
            for p in (("ACPI","DropTables"),("ACPI","SortedOrder"),("ACPI","DSDT","Patches")):
                print(" - {}...".format(" -> ".join(p)))
                config_data = self.ensure_path(config_data,p)
                target_data = self.ensure_path(target_data,p)
            # Set up our patch sources
            ssdts = target_data["ACPI"]["SortedOrder"]
            patch = target_data["ACPI"]["DSDT"]["Patches"]
            drops = target_data["ACPI"]["DropTables"]
            # Set up our original values
            s_orig = config_data["ACPI"]["SortedOrder"]
            p_orig = config_data["ACPI"]["DSDT"]["Patches"]
            d_orig = config_data["ACPI"]["DropTables"]
        print("")
        if not ssdts:
            print("--- No SSDTs to add - skipping...")
        else:
            print("--- Walking target SSDTs ({:,} total)...".format(len(ssdts)))
            s_rem = []
            # Gather any entries broken from user error
            s_broken = [x for x in s_orig if not isinstance(x,dict)] if self.config_type == "OpenCore" else []
            for s in ssdts:
                if self.config_type == "OpenCore":
                    print(" - Checking {}...".format(s["Path"]))
                    existing = [x for x in s_orig if isinstance(x,dict) and x["Path"] == s["Path"]]
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
            if s_broken:
                errors_found = True
                print("\n{}!! WARNING !!{} {:,} Malformed entr{} found - please fix your {}!".format(
                    self.yel,
                    self.rst,
                    len(s_broken),
                    "y" if len(d_broken)==1 else "ies",
                    config_name
                ))
        print("")
        if not patch:
            print("--- No patches to add - skipping...")
        else:
            print("--- Walking target patches ({:,} total)...".format(len(patch)))
            p_rem = []
            # Gather any entries broken from user error
            p_broken = [x for x in p_orig if not isinstance(x,dict)]
            for p in patch:
                print(" - Checking {}...".format(p["Comment"]))
                if self.config_type == "OpenCore" and self.check_normalize(p,normalize_headers):
                    errors_found = True
                existing = [x for x in p_orig if isinstance(x,dict) and x["Find"] == p["Find"] and x["Replace"] == p["Replace"]]
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
            if p_broken:
                errors_found = True
                print("\n{}!! WARNING !!{} {:,} Malformed entr{} found - please fix your {}!".format(
                    self.yel,
                    self.rst,
                    len(p_broken),
                    "y" if len(d_broken)==1 else "ies",
                    config_name
                ))
        print("")
        if not drops:
            print("--- No tables to drop - skipping...")
        else:
            print("--- Walking target tables to drop ({:,} total)...".format(len(drops)))
            d_rem = []
            # Gather any entries broken from user error
            d_broken = [x for x in d_orig if not isinstance(x,dict)]
            for d in drops:
                if self.config_type == "OpenCore":
                    print(" - Checking {}...".format(d["Comment"]))
                    if self.check_normalize(d,normalize_headers,check_type="Dropped table"):
                        errors_found = True
                    existing = [x for x in d_orig if isinstance(x,dict) and x["TableSignature"] == d["TableSignature"] and x["OemTableId"] == d["OemTableId"]]
                else:
                    name = " - ".join([x for x in (d.get("Signature",""),d.get("TableId","")) if x]) or "Unknown Dropped Table"
                    print(" - Checking {}...".format(name))
                    existing = [x for x in d_orig if isinstance(x,dict) and x.get("Signature") == d.get("Signature") and x.get("TableId") == d.get("TableId")]
                if existing:
                    print(" --> Located {:,} existing to replace...".format(len(existing)))
                    d_rem.extend(existing)
            if d_rem:
                print(" - Removing {:,} existing duplicate{}...".format(len(d_rem),"" if len(d_rem)==1 else "s"))
                for r in d_rem:
                    if r in d_orig: d_orig.remove(r)
            else:
                print(" - No duplicates to remove...")
            print(" - Dropping {:,} table{}...".format(len(drops),"" if len(drops)==1 else "s"))
            d_orig.extend(drops)
            if d_broken:
                errors_found = True
                print("\n{}!! WARNING !!{} {:,} Malformed entr{} found - please fix your {}!".format(
                    self.yel,
                    self.rst,
                    len(d_broken),
                    "y" if len(d_broken)==1 else "ies",
                    config_name
                ))
        print("")
        if self.overwrite:
            output_path = self.config_path
        else:
            config_name = self.get_unique_name(config_name,self.output)
            output_path = os.path.join(self.output,config_name)
        print("Saving to {}...".format(output_path))
        try:
            plist.dump(config_data,open(output_path,"wb"))
        except Exception as e:
            print(" - Failed to save! {}".format(e))
            return self.pause_interactive()
        print(" - Saved.")
        print("")
        if errors_found:
            print("{}!! WARNING !!{} Potential errors were found when merging - please address them!".format(
                self.yel,
                self.rst
            ))
            print("")
        if not self.overwrite:
            print("{}!! WARNING !!{} Make sure you review the saved {} before replacing!".format(
                self.red,
                self.rst,
                config_name
            ))
            print("")
        print("Done.")
        return self.pause_interactive()

    def get_plist_info(self, config_path):
        # Attempts to load the passed config and return a tuple
        # of (type_string,config_data,error)
        type_string = config_data = e = None
        try:
            config_data = plist.load(open(config_path,"rb"))
        except Exception as e:
            return (None,None,e)
        if not isinstance(config_data,dict):
            e = "Invalid root node type: {}".format(type(config_data))
        else:
            type_string = "OpenCore" if "PlatformInfo" in config_data else "Clover" if "SMBIOS" in config_data else None
        return (type_string,config_data,None)

    def get_patch_plist_for_type(self, path, config_type):
        o,c = self._get_patches_plists(path)
        return {
            "OpenCore":o,
            "Clover":c
        }.get(config_type,(None,False,None))

    def select_plist(self):
        while True:
            self.u.head("Select Plist")
            print("")
            if self.copy_as_path:
                print("NOTE:  Currently running as admin on Windows - drag and drop may not work.")
                print("       Shift + right-click in Explorer and select 'Copy as path' then paste here instead.")
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
                self.u.grab("Press [enter] to return...")
                continue
            # Got a file - try to load it
            t,_,e = self.get_plist_info(test_path)
            if e:
                self.u.head("Invalid File")
                print("")
                print("That file failed to load:\n\n{}".format(e))
                print("")
                self.u.grab("Press [enter] to return...")
                continue
            # Got a valid file
            self.config_path = test_path
            self.config_type = t
            return

    def main(self):
        # Gather some preliminary info for display
        target_path,target_exists,target_name = self.get_patch_plist_for_type(
            self.output,
            self.config_type
        )
        self.u.resize(self.w,self.h)
        self.u.head()
        print("")
        print("Current config.plist:  {}".format(self.config_path))
        print("Type of config.plist:  {}".format(self.config_type or "Unknown"))
        print("Results Folder:        {}".format(self.output))
        print("Patches Plist:         {}{}".format(
            target_name or "Unknown",
            "" if (not target_name or target_exists) else " - {}!! MISSING !!{}".format(self.red,self.rst)
        ))
        print("Overwrite Original:    {}{}{}{}".format(
            self.red if self.overwrite else self.grn,
            "!! True !!" if self.overwrite else "False",
            self.rst,
            " - Make Sure You Have A Backup!" if self.overwrite else ""
        ))
        print("")
        print("C. Select config.plist")
        print("O. Toggle Overwrite Original")
        print("R. Select Results Folder")
        if self.config_path and target_exists:
            print("P. Patch with {}".format(target_name))
        print("")
        print("Q. Quit")
        print("")
        menu = self.u.grab("Please make a selection:  ")
        if not len(menu):
            return
        if menu.lower() == "q":
            self.u.custom_quit()
        elif menu.lower() == "c":
            self.select_plist()
        elif menu.lower() == "o":
            self.overwrite ^= True
        elif menu.lower() == "r":
            self.select_results_folder()
        elif menu.lower() == "p" and self.config_path and target_exists:
            self.patch_plist()

if __name__ == '__main__':
    # Setup the cli args
    parser = argparse.ArgumentParser(prog="PatchMerge.py", description="PatchMerge - py script to merge patches_[OC/Clover].plist with a config.plist.")
    parser.add_argument("-c", "--config", help="path to target config.plist - required if running in non-interactive mode")
    parser.add_argument("-r", "--results", help="path to Results folder containing patches_[OC/Clover].plist - required if running in non-interactive mode")
    parser.add_argument("-o", "--overwrite", help="overwrite the original config.plist", action="store_true")
    parser.add_argument("-i", "--no-interaction", help="run in non-interactive mode - requires -c and -r", action="store_true")

    args = parser.parse_args()

    p = PatchMerge(
        config=args.config,
        results=args.results,
        overwrite=args.overwrite,
        interactive=not args.no_interaction
    )

    if args.no_interaction:
        # We're in non-interactive mode here
        p.patch_plist()
    else:
        # Interactive mode
        if 2/3 == 0:
            input = raw_input
        while True:
            try:
                p.main()
            except Exception as e:
                print("An error occurred: {}".format(e))
                print("")
                input("Press [enter] to continue...")
