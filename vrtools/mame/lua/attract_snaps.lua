-- Leave the game in attract mode and snapshot every VR_SNAP_EVERY frames from VR_SNAP_FROM to VR_SNAP_TO (no input).
local from  = tonumber(os.getenv("VR_SNAP_FROM") or "1800")
local to    = tonumber(os.getenv("VR_SNAP_TO") or "4200")
local every = tonumber(os.getenv("VR_SNAP_EVERY") or "20")
local frame = 0
emu.register_frame_done(function()
  frame = frame + 1
  if frame >= from and frame <= to and (frame - from) % every == 0 then manager.machine.video:snapshot() end
end)
-- Phase 28 fix wave: the arcade's rate in the attract (tests/test_frame_rate.py): the frame and render-rate logs, when asked for.
local lua_dir = os.getenv("VR_LUA_DIR")
if os.getenv("VR_FRAME_LOG") and lua_dir then dofile(lua_dir .. "/frame_rate.lua") end
if os.getenv("VR_RATE_LOG") and lua_dir then dofile(lua_dir .. "/renderrate.lua") end
if os.getenv("VR_SOUND_LOG") and lua_dir then dofile(lua_dir .. "/sound_log.lua") end   -- Phase 37
