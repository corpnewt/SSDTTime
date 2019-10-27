SSDTTime
==========
A simple tool designed to make creating SSDTs simple.
Supports macOS, Linux and Windows

### Supported SSDTs:
- SSDT-EC
    - OS-aware fake EC
- SSDT-PLUG
    - Sets plugin-type = 1 on CPU0/PR00
- SSDT-HPET
    - Patches out IRQ conflicts
    
Additionally on Linux and Windows the tool can be used to dump the system DSDT.

### Credits:
- [CorpNewt](https://github.com/CorpNewt) - Writing the script and libraries used
- [NoOne](https://github.com/IOIIIO) - Some small improvements to the script
- Rehabman/Intel - iasl
