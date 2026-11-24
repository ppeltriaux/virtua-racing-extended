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
if os.getenv("VR_STALE_LOG") and lua_dir then dofile(lua_dir .. "/stale_list.lua") end   -- Phase 79
if os.getenv("VR_STORM_LOG") and lua_dir then dofile(lua_dir .. "/storm_log.lua") end   -- weather stage 2: the storm, pass by pass
if os.getenv("VR_RATE_LOG") and lua_dir then dofile(lua_dir .. "/renderrate.lua") end
if os.getenv("VR_SOUND_LOG") and lua_dir then dofile(lua_dir .. "/sound_log.lua") end   -- Phase 37
-- the final review's W3 (tests/test_weather_dry.py's attract identity): the game's state at every pass end, the sound board's writes
-- (pcm_log.lua through VR_EXTRA_LUA) and, with VR_ATTRACT_LOG, "A <frame> <mode 0x501138 hex> <menu entry 0x501940>" at each frame
-- end where either changed (which demo races the attract showed)
if os.getenv("VR_PASS_LOG") and lua_dir then dofile(lua_dir .. "/pass_state.lua") end
if os.getenv("VR_EXTRA_LUA") then for p in string.gmatch(os.getenv("VR_EXTRA_LUA"), "[^;]+") do dofile(p) end end
if os.getenv("VR_ATTRACT_LOG") then
  local aout = assert(io.open(os.getenv("VR_ATTRACT_LOG"), "w"))
  local aprog = manager.machine.devices[":maincpu"].spaces["program"]
  local af, alast = 0, ""
  emu.register_frame_done(function()
    af = af + 1
    local s = string.format("%02x %d", aprog:read_u8(0x501138), aprog:read_u8(0x501940))
    if s ~= alast then aout:write(string.format("A %d %s\n", af, s)); aout:flush(); alast = s end
  end)
end
