-- Weather stage 3, fix round 1 (tests/test_weather_cover.py): the storm's generator word set to a chosen value, so that a measure
-- over the rain's random placement can be taken on several generator trajectories of the same (taped) game. Pictures only: the
-- generator is the storm's own (weather/rain.py's RAND cell), which nothing of the game reads. Loaded with VR_EXTRA_LUA. Env:
--   VR_STORM_SEED   "<hex address>:<hex value>[:<frame>]": write the value at that address once, at the end of the given frame (MAME
--                   frames from 1, autoplay.lua's), or without a frame at the end of the race load's pass: the first frame end at
--                   which the carrier's STATE byte (VR_STORM_STATE, hex) reads 1 (STARTING: the load zeroed the cells, the
--                   rain's start passes, which draw the first placements, have not run)
--   VR_SEED_LOG     path: "SEED <frame> <address> <value>" when written
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local at, value, when = string.match(assert(os.getenv("VR_STORM_SEED"), "storm_seed.lua: VR_STORM_SEED is not set"),
  "^(%x+):(%x+):?(%d*)$")
assert(at, "storm_seed.lua: VR_STORM_SEED is <hex address>:<hex value>[:<frame>]")
at, value, when = tonumber(at, 16), tonumber(value, 16), tonumber(when)
local state = tonumber(os.getenv("VR_STORM_STATE") or "", 16)
assert(when or state, "storm_seed.lua: no frame and no VR_STORM_STATE")
local log_path = os.getenv("VR_SEED_LOG")
local frame, done = 0, false
emu.register_frame_done(function()
  frame = frame + 1
  if done then return end
  if (when and frame == when) or (not when and mem:read_u8(state) == 1) then
    mem:write_u32(at, value)
    done = true
    if log_path then
      local f = assert(io.open(log_path, "w"))
      f:write(string.format("SEED %d %x %x\n", frame, at, value))
      f:close()
    end
  end
end)
