-- Steer at a place (Phase 22a: the wall gate). Loaded with VR_EXTRA_LUA after autoplay.lua, so its frame callback runs
-- after the autopilot's: once the player (_G.vr_player, from collision_log.lua) comes within 12 units of
-- VR_STEER_AT="x:z:value:frames", the paddle holds `value` for `frames` frames, once. Phase 26: with VR_STEER_LOG (path) it writes
-- "S <frame> <race start>" when the hold begins (frames from 1 as race_log.lua's; the race start is autoplay.lua's).
local x, z, val, n = string.match(os.getenv("VR_STEER_AT") or "", "([-%d.]+):([-%d.]+):(%d+):(%d+)")
assert(x, "VR_STEER_AT=x:z:value:frames")
x, z, val, n = tonumber(x), tonumber(z), tonumber(val), tonumber(n)
local wheel
for name, f in pairs(manager.machine.ioport.ports[":WHEEL"].fields) do if name == "Paddle" then wheel = f end end
local left, frame = nil, 0
local log_path = os.getenv("VR_STEER_LOG")
emu.register_frame_done(function()
  frame = frame + 1
  local p = _G.vr_player
  if left == nil and p and (p.x - x) ^ 2 + (p.z - z) ^ 2 < 144 then
    left = n
    if log_path then
      local f = assert(io.open(log_path, "w"))
      f:write(string.format("S %d %s\n", frame, tostring(type(_G.vr_race_start) == "function" and _G.vr_race_start() or -1))); f:close()
    end
  end
  if left and left > 0 then wheel:set_value(val); left = left - 1 end
end)
