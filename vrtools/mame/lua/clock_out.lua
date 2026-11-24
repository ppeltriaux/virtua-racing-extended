-- Weather stage 2: a race ended by time over at a chosen moment. At the frame end VR_CLOCK_OUT frames after the race start
-- (autoplay.lua's `vr_race_start`), the race clock 0x50116c is set to 1 (1/32 s left), so the game's time over follows at once.
-- Loaded with VR_EXTRA_LUA alongside autoplay.lua.
local after = tonumber(os.getenv("VR_CLOCK_OUT") or "")
if not after then error("clock_out.lua: VR_CLOCK_OUT is missing") end
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local frame, done = 0, false
emu.register_frame_done(function()
  frame = frame + 1
  local start = _G.vr_race_start and _G.vr_race_start()
  if not done and start and frame == start + after then mem:write_u32(0x50116c, 1); done = true end
end)
