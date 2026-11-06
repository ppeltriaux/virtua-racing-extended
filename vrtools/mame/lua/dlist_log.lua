-- Dump the active Model 1 display list every VR_DLIST_EVERY frames from VR_DLIST_FROM on.
-- Output line: "F <frame> <list_base_hex> <0x8000 big-endian hex u16 entries>"
local out_path = os.getenv("VR_DLIST_LOG")
if out_path then
  local from  = tonumber(os.getenv("VR_DLIST_FROM") or "1400")
  local every = tonumber(os.getenv("VR_DLIST_EVERY") or "10")
  local out = assert(io.open(out_path, "w"))
  local mem = manager.machine.devices[":maincpu"].spaces["program"]
  local frame = 0
  local fmt = string.format
  emu.register_frame_done(function()
    frame = frame + 1
    if frame < from or (frame - from) % every ~= 0 then return end
    local ctl = mem:read_u16(0x680000)
    local active = (ctl & 0x40) ~= 0 and 0x610000 or 0x600000
    local bases = os.getenv("VR_DLIST_BOTH") and {0x600000, 0x610000} or {active}   -- VR_DLIST_BOTH=1: dump both lists
    for _, base in ipairs(bases) do
      local parts = {}
      for i = 0, 0x7fff do
        parts[#parts + 1] = fmt("%04x", mem:read_u16(base + 2 * i))
      end
      out:write(fmt("F %d %x %s\n", frame, base, table.concat(parts)))
    end
    out:flush()
  end)
end
