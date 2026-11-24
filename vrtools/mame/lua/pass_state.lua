-- Phase 28: the game's state at the end of every logic pass, at the same point of every pass (the first read of 0x500501 in the
-- two-vblank wait, 0xfe13db..0xfe13f3), not at MAME's frame end:
--   W <pass> <frame> <clock 0x50116c> then, for each car 0..15 (entity 0x400d00 + 0x280 i): <x +0x1e> <z +0x26> (the f32's bits,
--   hex) <road point +0xa6> <speed +0x14> <lap +0x1b5>
-- pass counts the passes from 1; frame the MAME frame (from 1 at the first frame end) in which the pass ended. A frame-end log
-- samples the game inside a pass (MAME's frame end falls about 1.5 ms after the wait's exit, Phase 28 findings §6), so two sets
-- whose passes take different times can log different values there while the game is the same; this log cannot.
-- With VR_PASS_FIELDS=1 (the join's round 2, J4: tests/test_frame_rate.py compares at pass ends what fieldtrace.lua samples at
-- frame ends), after each car's five fields also: <line cursor +0xe1> <target +0x1b1> <lap-position quad +0x30> (u16, hex)
-- <working performance +0x48> (the f32's bits, hex) <rank +0x123> <the ranking neighbours +0x198, +0x19c> (u8 / u32, hex).
-- Env: VR_PASS_LOG (path), VR_PASS_FIELDS. The last line is "END".
local path = os.getenv("VR_PASS_LOG")
if path then
  local out = assert(io.open(path, "w"))
  local cpu = manager.machine.devices[":maincpu"]
  local prog = cpu.spaces["program"]
  local pcst = cpu.state["PC"]
  local frame, pass, in_wait = 0, 0, true
  local fields = os.getenv("VR_PASS_FIELDS") == "1"
  emu.register_frame_done(function() frame = frame + 1 end)
  _G.vr_pass_state_taps = {
    prog:install_read_tap(0x500500, 0x500501, "vr_ps_wait", function(offset, data, mask)
      if in_wait or (mask & 0xff00) == 0 then return end
      local pc = pcst.value
      if pc >= 0xfe13db and pc <= 0xfe13f3 then
        in_wait = true
        pass = pass + 1
        local t = {string.format("W %d %d %d", pass, frame, prog:read_i32(0x50116c))}
        for car = 0, 15 do
          local b = 0x400d00 + 0x280 * car
          t[#t + 1] = string.format("%08x %08x %d %d %d", prog:read_u32(b + 0x1e), prog:read_u32(b + 0x26), prog:read_u16(b + 0xa6),
            prog:read_u32(b + 0x14), prog:read_u8(b + 0x1b5))
          if fields then
            t[#t + 1] = string.format("%x %x %x %08x %x %x %x", prog:read_u16(b + 0xe1), prog:read_u16(b + 0x1b1), prog:read_u16(b + 0x30),
              prog:read_u32(b + 0x48), prog:read_u8(b + 0x123), prog:read_u32(b + 0x198), prog:read_u32(b + 0x19c))
          end
        end
        out:write(table.concat(t, " ") .. "\n")
        if pass % 50 == 0 then out:flush() end
      end
    end),
    prog:install_write_tap(0x500500, 0x500501, "vr_ps_exit", function(offset, data, mask)
      if (mask & 0xff00) == 0 or ((data >> 8) & 0xff) ~= 0 then return end
      local pc = pcst.value
      if pc >= 0xfe1400 and pc <= 0xfe140e then in_wait = false end
    end),
  }
  _G.vr_pass_state_stop = emu.add_machine_stop_notifier(function() out:write("END\n"); out:close() end)
end
