-- Phase 37 (after the review, whose staging this follows: the wheel held and the off-course limit poked to 3): a put-back staged
-- at a chosen place of a race. Loaded with VR_EXTRA_LUA alongside autoplay.lua, whose frame callback runs first, so the wheel
-- set here is the one the game reads. Env:
--   VR_PUTBACK_QUAD   decimal: from the first frame end of the race (mode 0x14) at which the player's lap-position quad (+0x30)
--                     is this one, the paddle is held at VR_PUTBACK_WHEEL for VR_PUTBACK_FRAMES frames (once in the run)
--   VR_PUTBACK_WHEEL  the paddle value held (default 255)
--   VR_PUTBACK_FRAMES default 120
--   VR_PUTBACK_LIMIT  the off-course limit written to 0x50232c (course.OFF_COURSE_RAM) on every frame of the hold (default 3
--                     logic frames, the review's; the course's own, 128, is 4.3 s), and the course's own value written back after it
--   VR_PUTBACK_LOG    path: "H <frame>" at the hold's first frame, "B <frame> <quad before> <quad after>" at each frame end of the
--                     hold on which the put-back's timer 0x501160 has risen (the put-back, boot 0xfebcee: the remembered quad
--                     to +0x30, the counter 0x50115c to 0, 0x20 to the timer), "E <frame>" at the hold's end, then "END"
-- The trigger is a quad, not the tunnel flag, so the same staging runs on a set without the flag.
local quad = tonumber(os.getenv("VR_PUTBACK_QUAD") or "")
if quad then
  local mem = manager.machine.devices[":maincpu"].spaces["program"]
  local wheel = manager.machine.ioport.ports[":WHEEL"].fields["Paddle"]
  local value = tonumber(os.getenv("VR_PUTBACK_WHEEL") or "255")
  local frames = tonumber(os.getenv("VR_PUTBACK_FRAMES") or "120")
  local limit = tonumber(os.getenv("VR_PUTBACK_LIMIT") or "3")
  local out = os.getenv("VR_PUTBACK_LOG") and assert(io.open(os.getenv("VR_PUTBACK_LOG"), "w")) or nil
  local frame, from, own, timer, last_quad = 0, nil, nil, 0, 0
  local b = 0x400d00
  local function log(s) if out then out:write(s .. "\n"); out:flush() end end
  emu.register_frame_done(function()
    frame = frame + 1
    local q, t = mem:read_u16(b + 0x30), mem:read_u32(0x501160)
    if not from and mem:read_u8(0x501139) == 0x14 and q == quad then
      from, own = frame, mem:read_u32(0x50232c)
      log(string.format("H %d", frame))
    end
    if from and frame < from + frames then
      wheel:set_value(value)
      mem:write_u32(0x50232c, limit)
      if t > timer and frame > from then log(string.format("B %d %d %d", frame, last_quad, q)) end
    elseif from and frame == from + frames then
      mem:write_u32(0x50232c, own)
      log(string.format("E %d", frame))
    end
    timer, last_quad = t, q
  end)
  if out then _G.vr_putback_stop = emu.add_machine_stop_notifier(function() out:write("END\n"); out:close() end) end
end
