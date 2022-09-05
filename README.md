SSDTTime
==========
A simple tool designed to make creating SSDTs simple.
Supports macOS, Linux and Windows

## Supported SSDTs:
- SSDT-HPET
    - Patches out IRQ conflicts
- SSDT-EC
    - OS-aware fake EC (laptop and desktop variants)
- SSDT-USBX
    - Provides generic USB power properties
- SSDT-PLUG
    - Sets plugin-type = 1 on CPU0/PR00
- SSDT-PMC
    - Adds missing PMCR device for native 300-series NVRAM
- SSDT-AWAC
    - Disables AWAC clock, and enables (or fakes) RTC as needed
- SSDT-USB-Reset
    - Returns a zero status for detected root hubs to allow hardware querying
- SSDT-Bridge
    - Create missing PCI bridges for passed device path
- SSDT-PNLF
    - Sets up a PNLF device for laptop backlight control
- SSDT-XOSI
    - _OSI rename and patch to return true for a range of Windows versions - also checks for OSID
    
Additionally on Linux and Windows the tool can be used to dump the system DSDT.

## Instructions:
### Linux:
* Launch SSDTTime.py with any somewhat recent version of Python from either a terminal window or by running the file normally.
### macOS:
* Launch SSDTTime.command from either a terminal window or by double clicking the file.
### Windows:
* Launch SSDTTime.bat from either a terminal window or by double clicking the file.

## Credits:
- [CorpNewt](https://github.com/CorpNewt) - Writing the script and libraries used
- [NoOne](https://github.com/IOIIIO) - Some small improvements to the script
- Rehabman/Intel - iasl
