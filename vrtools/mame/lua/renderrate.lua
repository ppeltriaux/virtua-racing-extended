-- Render-rate probe: counts changes of the display-list select bit (0x680000 & 0x40) per 57 frames.
-- Sampled at frame_done, so a switch per frame reads as ~57/57; a switch every other frame as ~28/57.
-- Env: VR_RATE_LOG (absolute path). Lines: "R <frame> <switches>"; the last line is "END".
local path = os.getenv("VR_RATE_LOG")
if path then
  local out = assert(io.open(path, "w"))
  local mem = manager.machine.devices[":maincpu"].spaces["program"]
  local frame, last, switches = 0, nil, 0
  emu.register_frame_done(function()
    frame = frame + 1
    local bit = mem:read_u16(0x680000) & 0x40
    if last ~= nil and bit ~= last then switches = switches + 1 end
    last = bit
    if frame % 57 == 0 then out:write(string.format("R %d %d\n", frame, switches)); out:flush(); switches = 0 end
  end)
  emu.add_machine_stop_notifier(function() out:write("END\n"); out:close() end)
end
