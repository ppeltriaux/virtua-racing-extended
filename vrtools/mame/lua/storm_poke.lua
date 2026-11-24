-- Weather Task 6J (the join): forced states for the carrier's tests. Words written into the main CPU's memory at chosen frame ends,
-- e.g. the carrier's load key poked to another menu entry's during a RAIN race (the reload branch, not reached in the game's flow:
-- tests/test_weather_carrier.py::test_the_reload_branch_on_a_forced_state). Loaded with VR_EXTRA_LUA. Env:
--   VR_STORM_POKE   "<frame>:<hex address>:<hex value>[;...]": write the 32-bit value at that address at the end of that frame (MAME
--                   frames from 1, as autoplay.lua's and storm_log.lua's)
--   VR_POKE_LOG     path: "POKE <frame> <address> <value>" for each write made
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local spec = assert(os.getenv("VR_STORM_POKE"), "storm_poke.lua: VR_STORM_POKE is not set")
local pokes = {}
for item in string.gmatch(spec, "[^;]+") do
  local f, a, v = string.match(item, "^(%d+):(%x+):(%x+)$")
  assert(f, "storm_poke.lua: each item is <frame>:<hex address>:<hex value>, not " .. item)
  pokes[#pokes + 1] = {tonumber(f), tonumber(a, 16), tonumber(v, 16)}
end
local log_path = os.getenv("VR_POKE_LOG")
local log = log_path and assert(io.open(log_path, "w"))
local frame = 0
emu.register_frame_done(function()
  frame = frame + 1
  for _, p in ipairs(pokes) do
    if p[1] == frame then
      mem:write_u32(p[2], p[3])
      if log then log:write(string.format("POKE %d %x %x\n", frame, p[2], p[3])); log:flush() end
    end
  end
end)
