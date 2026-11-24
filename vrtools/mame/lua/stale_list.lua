-- Phase 79: the display list each pass of the main loop wrote, for the stale-list check (the rain spike's finding,
-- out/p48/look/NOTE.txt). After its two-vblank wait the game picks the list to write next from bit 6 of 0x680000 (read at
-- 0xff96f7), which MAME updates only at its screen update, about 18.9 ms after the wait's exit; a pass whose work runs past it
-- leaves the bit at the old list, and the next pass rewrites the list just submitted: MAME shows the other, frozen list on every
-- second render. The overrun counter and the render rate do not see it.
-- One line per pass, written at the exit of the wait that ends it (the write of 0 to 0x500501 from 0xfe1400..0xfe140e, the exit
-- frame_rate.lua times; the frame is the same as its F line's):
--   L <frame> <0x5017f4, hex>
-- 0x5017f4 is the game's write pointer into the display list (0x600000.. or 0x610000..); at the wait's exit it still points at
-- the end of the list the pass wrote (the next pass sets it to its own list's start after the pick). Two passes in a row in the
-- same list: a stale picture (runner.parse_stale_log). frame counts MAME frames from 1 at the first frame end. Env: VR_STALE_LOG
-- (path). The last line is "END".
local path = os.getenv("VR_STALE_LOG")
if path then
  local out = assert(io.open(path, "w"))
  local cpu = manager.machine.devices[":maincpu"]
  local prog = cpu.spaces["program"]
  local pcst = cpu.state["PC"]
  local frame, lines = 0, 0
  emu.register_frame_done(function() frame = frame + 1 end)
  _G.vr_stale_list_tap = prog:install_write_tap(0x500500, 0x500501, "vr_stale_exit", function(offset, data, mask)
    if (mask & 0xff00) == 0 or ((data >> 8) & 0xff) ~= 0 then return end
    local pc = pcst.value
    if pc >= 0xfe1400 and pc <= 0xfe140e then
      out:write(string.format("L %d %x\n", frame, prog:read_u32(0x5017f4)))
      lines = lines + 1
      if lines % 50 == 0 then out:flush() end
    end
  end)
  _G.vr_stale_list_stop = emu.add_machine_stop_notifier(function() out:write("END\n"); out:close() end)
end
