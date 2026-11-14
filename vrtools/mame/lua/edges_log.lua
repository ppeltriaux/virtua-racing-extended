-- Phase 26: what the edge code was given and returned, per car (entity 0x400d00 + 0x280 car). A write tap on +0x101 (the last of the
-- six result words; taps are 16-bit aligned, the lane mask picks the byte) snapshots +0x30 (the quad), +0x1e and +0x26 (x, z) as the 0x1500 call's own parameters; one on +0xeb (the
-- attribute, a halfword at +0xeb..+0xec: the game stores it with mov.h) snapshots +0x30. At the frame's end, for each car written that frame:
--   E <frame> <car> <quad> <x> <z> <+0xf1> <+0xed> <+0xf5> <+0xf9> <+0xfd> <+0x101> <attr quad> <attr> <edge frame> <attr frame>
-- frame, car and the two snapshot frames decimal; every other number raw hex (x, z the float bits; the six words in the order the call
-- returns them). Phase 26 (Task 8): seven of the fourteen direction sites are not preceded by a 0x1500 call, so a line written for an
-- attribute store alone carries the quad, x, z and six words of an earlier frame: <edge frame> is the frame whose 0x1500 call they come
-- from (0 if none yet), <attr frame> the same for <attr quad> and <attr>; a line is fresh for the edge values when <edge frame> == <frame>.
-- Frames count from 1 at the first frame end, as race_log.lua's (fieldtrace.lua's samples count from 0: its frame f is this frame f + 1).
-- Env: VR_EDGES_LOG (path).
local out_path = os.getenv("VR_EDGES_LOG")
if out_path then
  local out = assert(io.open(out_path, "w"))
  local mem = manager.machine.devices[":maincpu"].spaces["program"]
  local frame, snap, dirty = 0, {}, {}
  local function u32b(a) return mem:read_u8(a) | (mem:read_u8(a + 1) << 8) | (mem:read_u8(a + 2) << 16) | (mem:read_u8(a + 3) << 24) end   -- the words sit at odd offsets
  _G.vr_edges_taps = {}                                    -- kept so the taps are not collected
  for car = 0, 15 do
    local b = 0x400d00 + 0x280 * car
    snap[car] = {}
    _G.vr_edges_taps[#_G.vr_edges_taps + 1] = mem:install_write_tap(b + 0x100, b + 0x103, "edges_call" .. car, function(offset, data, mask)
      if offset ~= b + 0x100 or mask & 0xff00 == 0 then return end         -- the bus is 16 bits wide: only a write of the byte at +0x101 (the word's first)
      local s = snap[car]
      s.quad, s.x, s.z = mem:read_u16(b + 0x30), u32b(b + 0x1e), u32b(b + 0x26)
      s.edge_at = frame + 1                                                  -- this frame's line is written as frame + 1
      dirty[car] = true
    end)
    _G.vr_edges_taps[#_G.vr_edges_taps + 1] = mem:install_write_tap(b + 0xea, b + 0xeb, "edges_attr" .. car, function(offset, data, mask)
      if mask & 0xff00 == 0 then return end                                  -- the byte at +0xeb is the high lane of the halfword at +0xea
      snap[car].attr_quad, snap[car].attr_at = mem:read_u16(b + 0x30), frame + 1
      dirty[car] = true
    end)
  end
  emu.register_frame_done(function()
    frame = frame + 1
    local wrote = false
    for car = 0, 15 do
      if dirty[car] then
        local b, s = 0x400d00 + 0x280 * car, snap[car]
        out:write(string.format("E %d %d %x %x %x %x %x %x %x %x %x %x %x %d %d\n", frame, car, s.quad or 0, s.x or 0, s.z or 0,
          u32b(b + 0xf1), u32b(b + 0xed), u32b(b + 0xf5), u32b(b + 0xf9), u32b(b + 0xfd), u32b(b + 0x101),
          s.attr_quad or 0, mem:read_u8(b + 0xeb) | (mem:read_u8(b + 0xec) << 8), s.edge_at or 0, s.attr_at or 0))
        dirty[car], wrote = nil, true
      end
    end
    if wrote and frame % 20 == 0 then out:flush() end
  end)
end
