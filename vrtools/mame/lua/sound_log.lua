-- Phase 37: the V60's words to the sound board and the tunnel flag under the player's car. Loaded by autoplay.lua and
-- attract_snaps.lua when VR_SOUND_LOG names a file. The game sends a sound command as two bytes to the latch 0xc40000, the high
-- byte from PC 0xffa2a6 and the low byte from 0xffa36a on the next logic frame (recon, docs/spike/2026-11-phase37-tunnel-sound-
-- recon.md §1.2). Lines (frames decimal, counted from 1 at the first frame end as autoplay.lua's; the rest hex but the road point):
--   S <frame> <byte> <pc>     a byte written to the latch
--   F <frame> <mode 0x501139> <gate 0x501120> <handler +0xa> <quad +0x30> <flag +0x152> <previous flag +0x195> <road point +0xa6>
--                             the player (entity 0x400d00) at a frame end, written when any of the first six differs from the
--                             last F line (so every change of the flag under the car, of the mode and of the handler is there)
-- VR_SOUND_TIMEOUT=1 (a test's switch): on the first frame end of a race (mode 0x14) at which the flag under the car has bit 7,
-- the race clock 0x50116c is written 2, once: the race runs out of time inside a tunnel stretch.
-- The last line is "END".
local path = os.getenv("VR_SOUND_LOG")
if path then
  local out = assert(io.open(path, "w"))
  local cpu = manager.machine.devices[":maincpu"]
  local mem = cpu.spaces["program"]
  local frame, last, timed = 0, "", os.getenv("VR_SOUND_TIMEOUT") ~= "1"
  _G.vr_sound_taps = {mem:install_write_tap(0xc40000, 0xc40001, "sound_log", function(offset, data, mask)
    if mask & 0xff ~= 0 then out:write(string.format("S %d %x %x\n", frame + 1, data & 0xff, cpu.state["PC"].value)) end
  end)}
  local b = 0x400d00
  emu.register_frame_done(function()
    frame = frame + 1
    local mode, flag = mem:read_u8(0x501139), mem:read_u16(b + 0x152)
    local key = string.format("%x %x %x %x %x %x", mode, mem:read_u32(0x501120), mem:read_u32(b + 0xa), mem:read_u16(b + 0x30), flag,
      mem:read_u16(b + 0x195))
    if key ~= last then
      last = key
      out:write(string.format("F %d %s %d\n", frame, key, mem:read_i16(b + 0xa6)))
    end
    if not timed and mode == 0x14 and flag & 0x80 ~= 0 then mem:write_u32(0x50116c, 2); timed = true end
    if frame % 200 == 0 then out:flush() end
  end)
  _G.vr_sound_log_stop = emu.add_machine_stop_notifier(function() out:write("END\n"); out:close() end)
end
