-- Phase 28 fix wave: the autopilot's wheel and pedal on a tape, recorded on one run and fed back frame for frame on another, so
-- that two sets can be compared on exactly the same inputs (the autopilot's own steering depends on when, within MAME's frame, the
-- player's TGP calls fall: collision_log.lua groups them by MAME's frame end, and a set whose passes take another time can see a
-- position one frame earlier or later and steer otherwise; Phase 28 findings §13).
-- Loaded by autoplay.lua after autopilot.lua; it wraps _G.vr_autopilot_wheel and _G.vr_autopilot_throttle, which autoplay.lua calls
-- in its frame callback from the race start + 2 (everything before the race start is autoplay.lua's fixed schedule).
--   VR_INPUT_LOG (path): every call is written as  I <frame> <wheel or -> <throttle>  (frame: MAME frames from 1, as autoplay.lua's;
--     "-" when the autopilot had no position yet and left the wheel alone). The last line is "END".
--   VR_INPUT_REPLAY (path, a VR_INPUT_LOG): the autopilot is not consulted; each call returns the tape's value for that frame. A call
--     at a frame the tape does not have ends MAME with status 3 and a message on stderr (the two runs did not reach the race on the
--     same frame: not the same inputs). With VR_INPUT_LOG as well, the replay writes what it fed: the same tape, line for line, when
--     the run asked for every line of it (tests/test_frame_rate.py compares the two).
local log_path, replay_path = os.getenv("VR_INPUT_LOG"), os.getenv("VR_INPUT_REPLAY")
if log_path or replay_path then
  local frame = 0
  local wheel_now, lines = nil, 0
  -- registered before autoplay.lua's own callback, which therefore reads this frame's number
  emu.register_frame_done(function() frame = frame + 1; wheel_now = nil end)
  local function fail(msg)
    io.stderr:write("input_tape.lua: " .. msg .. "\n"); io.stderr:flush(); os.exit(3)
  end
  local wheel_fn, throttle_fn = _G.vr_autopilot_wheel, _G.vr_autopilot_throttle
  local tape, last_frame = nil, 0
  if replay_path then
    tape = {}
    for line in io.lines(replay_path) do
      local f, w, t = line:match("^I (%d+) (%S+) (%d+)$")
      if f then tape[tonumber(f)] = {w ~= "-" and tonumber(w) or nil, tonumber(t)}; last_frame = math.max(last_frame, tonumber(f)) end
    end
    assert(last_frame > 0, "input_tape.lua: an empty tape: " .. replay_path)
  end
  local out = log_path and assert(io.open(log_path, "w")) or nil
  local function entry()
    local e = tape[frame]
    if not e then fail(string.format("frame %d asks for an input, the tape %s has no line for it", frame, replay_path)) end
    return e
  end
  _G.vr_autopilot_wheel = function()
    if tape then
      wheel_now = entry()[1]
    else
      wheel_now = wheel_fn and wheel_fn() or nil
    end
    return wheel_now
  end
  _G.vr_autopilot_throttle = function()
    local t
    if tape then t = entry()[2] else t = throttle_fn and throttle_fn() or 255 end
    if out then
      out:write(string.format("I %d %s %d\n", frame, wheel_now and tostring(wheel_now) or "-", t))
      lines = lines + 1
      if lines % 100 == 0 then out:flush() end
    end
    return t
  end
  _G.vr_input_tape_stop = emu.add_machine_stop_notifier(function()
    if out then out:write("END\n"); out:close() end
  end)
end
