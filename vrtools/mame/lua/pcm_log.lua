-- Weather stage 6: the sound board's MultiPCM writes and the V60's sound latch, with the emulated time, for the storm's sound tests.
-- Loaded with VR_EXTRA_LUA alongside autoplay.lua when VR_PCM_LOG names a file. The 68000 writes each chip through three ports
-- (chip 1 at 0xc40000, chip 2 at 0xc60000, the byte lanes of 0..7: port 0 data, 1 the voice selector, 2 the register, MAME's
-- multipcm_device::write); a data write goes to the selected voice's selected register (0 pan, 1 sample, 2/3 pitch, 4 key on bit 7,
-- 5 level: total level = value >> 1, bit 0 set = no interpolation, 6/7 LFO). The V60 sends a sound word as two bytes to the latch
-- 0xc40000, the high byte from PC 0xffa2a6, the low byte from 0xffa36a (sound_log.lua). Lines (frames decimal, counted from 1 at the
-- first frame end as autoplay.lua's, the line's frame the one in progress; times in seconds of emulated time; the rest hex):
--   B <time>                                  this script started (a soft reset starts it again: the log is appended to)
--   P <frame> <time> <chip 1|2> <voice selector> <register> <value>   a data write
--   S <frame> <time> <byte> <pc>              a byte written to the V60's sound latch
--   M <frame> <time> <mode 0x501138>          the mode at a frame end where it changed
--   F <frame> <time>                          every frame end (the frame / time map of a WAV)
-- The last line is "END".
local path = os.getenv("VR_PCM_LOG")
if path and _G.vr_pcm then                      -- a soft reset ran the scripts again in the same Lua state: the taps and the frame
  _G.vr_pcm.frame = 0                           -- callback stand; the frames count from 1 again, as autoplay.lua's
  _G.vr_pcm.out:write(string.format("B %.6f\n", manager.machine.time:as_double()))
elseif path then
  local st = {out = assert(io.open(path, "a")), frame = 0, mode = -1}
  _G.vr_pcm = st
  local out = st.out
  local main = manager.machine.devices[":maincpu"]
  local mem = main.spaces["program"]
  local snd = manager.machine.devices[":m1audio:sndcpu"].spaces["program"]
  local sel, reg = {0, 0}, {0, 0}
  local function t() return manager.machine.time:as_double() end
  out:write(string.format("B %.6f\n", t()))
  local function tap(chip, base)
    return snd:install_write_tap(base, base + 7, "pcm_log" .. chip, function(offset, data, mask)
      local port, v = (offset - base) // 2, data & 0xff
      if port == 1 then sel[chip] = v & 0x1f
      elseif port == 2 then reg[chip] = v
      elseif port == 0 then out:write(string.format("P %d %.6f %d %x %x %x\n", st.frame + 1, t(), chip, sel[chip], reg[chip], v)) end
    end)
  end
  st.taps = {tap(1, 0xc40000), tap(2, 0xc60000),
    mem:install_write_tap(0xc40000, 0xc40001, "pcm_log_latch", function(offset, data, mask)
      if mask & 0xff ~= 0 then out:write(string.format("S %d %.6f %x %x\n", st.frame + 1, t(), data & 0xff, main.state["PC"].value)) end
    end)}
  st.frame_cb = emu.register_frame_done(function()
    st.frame = st.frame + 1
    local m = mem:read_u8(0x501138)
    if m ~= st.mode then st.mode = m; out:write(string.format("M %d %.6f %x\n", st.frame, t(), m)) end
    out:write(string.format("F %d %.6f\n", st.frame, t()))
    if st.frame % 300 == 0 then out:flush() end
  end)
  st.stop = emu.add_machine_stop_notifier(function() out:write("END\n"); out:close() end)
end
