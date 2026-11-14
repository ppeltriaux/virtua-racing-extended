-- Phase 26: the attract cycle with the direction flag held on (standalone, no coin). Every frame writes 1 to the flag byte
-- VR_FLAG_RAM (hex) and sets the menu entry [0x501940] to the original whose data index is ([0x501934] + 1) % 3
-- (VR_FLAG_MENU=next) or [0x501934] (same), through the directory's FALLBACK (1, 2, 0), so that a course load can take the
-- directory's menu path, where the flag is read. Both writes stop from a change of bank (0xe00004, low nibble 1, as
-- memtrace.lua reads it) until the loader's write of map_tx (0x50231c): the backdrop upload between the bank switch and the
-- loader spans a frame boundary, and the real game writes neither byte there. One line per loader write, at the end of
-- its frame, to VR_FLAG_LOG:
--   L <frame> <data index> <menu> <map_tx> <mode [0x501138]> <next mode [0x501139]> <caller>
-- (data index, menu, modes and caller as the loader's write saw them; caller = the loader's return address, at SP + 12
-- under its three pushes; map_tx = the float the loader wrote). The two mode bytes: the dispatcher (0xfe1c7d) copies
-- 0x501139 to 0x501138 and runs the handler of 0x501138, and a handler changes mode by writing 0x501139. The loader runs
-- inside a mode handler (2 and 6 in the attract, 0x11 in a game), so 0x501138 is the mode the load ran in (the test's mode-6
-- check reads it) and 0x501139 the mode that handler has requested next; direction.lua reads 0x501139 alone, between dispatches.
local cpu = manager.machine.devices[":maincpu"]
local mem = cpu.spaces["program"]
local flag_ram = tonumber(os.getenv("VR_FLAG_RAM"), 16)
local ahead = os.getenv("VR_FLAG_MENU") == "next"
local fallback = {[0] = 1, [1] = 2, [2] = 0}
local out = assert(io.open(os.getenv("VR_FLAG_LOG"), "w"))
local frame, bank, loading, seen = 0, nil, false, nil
_G.vr_flag_taps = {                                     -- kept reachable: a collected tap is removed
  mem:install_write_tap(0xe00004, 0xe00005, "flag_bank", function(offset, data, mask)
    if (data & 0xf) == 1 then
      local b = (data >> 4) & 7
      if b ~= bank then bank = b; loading = true end
    end
  end),
  mem:install_write_tap(0x50231c, 0x50231f, "flag_tx", function(offset, data, mask)
    if frame > 20 and not seen then                     -- (the boot's own copy of 149.0 is at frame 9)
      seen = {mem:read_u8(0x501934), mem:read_u8(0x501940), mem:read_u8(0x501138), mem:read_u8(0x501139),
              mem:read_u32(cpu.state["SP"].value + 12)}
    end
  end)}
local function f32(u) return (string.unpack("<f", string.pack("<I4", u))) end
emu.register_frame_done(function()
  frame = frame + 1
  if seen then
    out:write(string.format("L %d %d %d %.3f %d %d %x\n", frame, seen[1], seen[2], f32(mem:read_u32(0x50231c)), seen[3], seen[4], seen[5]))
    out:flush()
    seen, loading = nil, false
  end
  if loading then return end
  mem:write_u8(flag_ram, 1)
  local di = mem:read_u8(0x501934)
  if di < 3 then mem:write_u8(0x501940, fallback[ahead and (di + 1) % 3 or di]) end
end)
