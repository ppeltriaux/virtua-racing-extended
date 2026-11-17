-- Phase 28: the arcade's rate, frame by frame. One line per logic frame (one pass of the main loop, 0xfe11ff..0xfe13d9, which ends
-- in the two-vblank wait at 0xfe13db):
--   F <frame> <busy us> <overrun 0x501148> <records 0x5011a0, the frame's peak> <lists skipped> <budget 0x5011b0> <need>
-- busy: emulated time from the wait's exit (`mov.b #0, 500501` at 0xfe1406) to the next entry into it (its first read of 0x500501,
-- from 0xfe13db..0xfe13f3), in microseconds; two vblanks are 34 770 us. overrun: the game's own counter, incremented at 0xfe13fe
-- when the work took more than two vblanks. records: the highest value the frame's record count reached. lists skipped: object
-- lists the walker (0xff848a / 0xff84a2) entered with the count already above the budget, which it then does not draw. need: the
-- least budget under which the frame skips no list, the highest count the walker compared (a frame with need above 5 500 is one
-- the game's own budget would have cut). Not counted in either: the character path's own check at 0xff5e33 (an object with flag
-- bit 0x1a drawn only while the count is at most the budget less 150; the scratch logger p28b_frame.lua counted it, and it never
-- ran in the measured races).
-- frame counts MAME frames from 1 at the first frame end (as renderrate.lua and race_log.lua). The line of a pass is written when
-- the next pass leaves the wait. Env: VR_FRAME_LOG (path). The last line is "END".
-- VR_HOLD_CLOCK=1 (a harness switch, as the Phase 28 recon's): the race clock 0x50116c (1/32 s) is put back to 60 s whenever it
-- falls below 30 s during a race, so that an autopilot that cannot overtake races on to the run's end instead of timing out.
local path = os.getenv("VR_FRAME_LOG")
if path then
  local out = assert(io.open(path, "w"))
  local cpu = manager.machine.devices[":maincpu"]
  local prog = cpu.spaces["program"]
  local pcst = cpu.state["PC"]
  local function now() return manager.machine.time:as_double() end
  local frame, in_wait, t_exit, t_enter = 0, true, nil, nil
  local count, peak, skipped, need, lines = 0, 0, 0, 0, 0
  emu.register_frame_done(function() frame = frame + 1 end)
  local function finish()
    if t_exit and t_enter then
      out:write(string.format("F %d %.0f %d %d %d %d %d\n", frame, (t_enter - t_exit) * 1e6, prog:read_u32(0x501148), peak, skipped,
        prog:read_u32(0x5011b0), need))
      lines = lines + 1
      if lines % 50 == 0 then out:flush() end
    end
    peak, skipped, need = 0, 0, 0
  end
  _G.vr_frame_rate_taps = {
    prog:install_read_tap(0x500500, 0x500501, "vr_fr_wait", function(offset, data, mask)
      if in_wait or (mask & 0xff00) == 0 then return end
      local pc = pcst.value
      if pc >= 0xfe13db and pc <= 0xfe13f3 then in_wait = true; t_enter = now() end
    end),
    prog:install_write_tap(0x500500, 0x500501, "vr_fr_exit", function(offset, data, mask)
      if (mask & 0xff00) == 0 or ((data >> 8) & 0xff) ~= 0 then return end
      local pc = pcst.value
      if pc >= 0xfe1400 and pc <= 0xfe140e then finish(); t_exit = now(); in_wait = false; t_enter = nil end
    end),
    prog:install_write_tap(0x5011a0, 0x5011a1, "vr_fr_count", function(offset, data, mask)
      count = data
      if data > peak then peak = data end
    end),
    prog:install_read_tap(0x5011b0, 0x5011b1, "vr_fr_budget", function(offset, data, mask)
      if offset ~= 0x5011b0 or (mask & 0xffff) == 0 then return end
      local pc = pcst.value
      if (pc >= 0xff848a and pc < 0xff8496) or (pc >= 0xff84a2 and pc < 0xff84ae) then
        if count > data then skipped = skipped + 1 end
        if count > need then need = count end
      end
    end),
  }
  _G.vr_frame_rate_stop = emu.add_machine_stop_notifier(function() out:write("END\n"); out:close() end)
end
if os.getenv("VR_HOLD_CLOCK") == "1" then
  local mem = manager.machine.devices[":maincpu"].spaces["program"]
  emu.register_frame_done(function()
    local c = mem:read_i32(0x50116c)
    if c > 0 and c < 960 then mem:write_i32(0x50116c, 1920) end
  end)
end
