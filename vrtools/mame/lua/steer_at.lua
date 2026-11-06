-- Steer at a place (Phase 22a: the wall gate). Loaded with VR_EXTRA_LUA after autoplay.lua, so its frame callback runs
-- after the autopilot's: once the player (_G.vr_player, from collision_log.lua) comes within 12 units of
-- VR_STEER_AT="x:z:value:frames", the paddle holds `value` for `frames` frames, once.
local x, z, val, n = string.match(os.getenv("VR_STEER_AT") or "", "([-%d.]+):([-%d.]+):(%d+):(%d+)")
assert(x, "VR_STEER_AT=x:z:value:frames")
x, z, val, n = tonumber(x), tonumber(z), tonumber(val), tonumber(n)
local wheel
for name, f in pairs(manager.machine.ioport.ports[":WHEEL"].fields) do if name == "Paddle" then wheel = f end end
local left = nil
emu.register_frame_done(function()
  local p = _G.vr_player
  if left == nil and p and (p.x - x) ^ 2 + (p.z - z) ^ 2 < 144 then left = n end
  if left and left > 0 then wheel:set_value(val); left = left - 1 end
end)
