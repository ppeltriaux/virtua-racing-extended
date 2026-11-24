-- Weather stage 2 (the fallback round): buttons of :IN.0 / :IN.1 held at chosen frames, and MAME's soft reset, for the storm's
-- robustness tests (the TEST switch and its menu during and after a RAIN race; a reset). Loaded with VR_EXTRA_LUA. Env:
--   VR_TEST_INPUT  "frame:field:frames;...": the field (its MAME name: "Service Mode", "VR1 (Red)", "VR4 (Green)", "Coin 1", ...)
--                  held from that frame end for that many frames
--   VR_SOFT_RESET  "frame[,frame...]": MAME's soft reset at that frame end
-- Lines (VR_TEST_LOG, appended): I <frame> <field>, R <frame>. Frames count from 1 at the first frame end, as autoplay.lua's.
-- A soft reset runs the autoboot scripts again (their frames from 1 again, every log reopened): the log's R line keeps this script
-- from resetting a second time, and its inputs from being pressed again.
local log_path = assert(os.getenv("VR_TEST_LOG"), "test_inputs.lua: VR_TEST_LOG is not set")
local again = false
local old = io.open(log_path, "r")
if old then for line in old:lines() do if line:match("^R ") then again = true end end; old:close() end
local out = assert(io.open(log_path, "a"))
local function field(name)
  for _, tag in ipairs({":IN.0", ":IN.1"}) do
    for n, f in pairs(manager.machine.ioport.ports[tag].fields) do if n == name then return f end end
  end
  error("test_inputs.lua: no field " .. name)
end
local presses, resets = {}, {}
for f, name, n in string.gmatch(again and "" or os.getenv("VR_TEST_INPUT") or "", "(%d+):([^:;]+):(%d+)") do
  presses[#presses + 1] = {tonumber(f), field(name), name, tonumber(n)}
end
for f in string.gmatch(again and "" or os.getenv("VR_SOFT_RESET") or "", "%d+") do resets[tonumber(f)] = true end
local frame = 0
emu.register_frame_done(function()
  frame = frame + 1
  for _, p in ipairs(presses) do
    if frame == p[1] then p[2]:set_value(1); out:write(string.format("I %d %s\n", frame, p[3])) end
    if frame == p[1] + p[4] then p[2]:set_value(0) end
  end
  if resets[frame] then out:write(string.format("R %d\n", frame)); out:flush(); manager.machine:soft_reset() end
  out:flush()
end)
