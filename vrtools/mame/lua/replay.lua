-- Phase 22a: replay a recorded drive (mame -playback): the FIFO hook and the loggers of autoplay.lua, no inputs (the
-- recording drives them); snapshots every VR_SNAP_EVERY frames from VR_SNAP_FROM.
local lua_dir = os.getenv("VR_LUA_DIR")

-- One tap on the V60 -> TGP FIFO (0xd80010 low half, 0xd80012 high half). Other scripts register listeners
-- with vr_on_fifo_word(fn) and get (word, frame): a second tap on the same range does not fire.
local frame, race_start = 0, nil
local fifo_lo, fifo_want, fifo_listeners = nil, false, {}
_G.vr_on_fifo_word = function(fn) fifo_listeners[#fifo_listeners + 1] = fn end      -- the autoboot chunk has its own env
_G.vr_race_start = function() return race_start end
local prog = manager.machine.devices[":maincpu"].spaces["program"]
_G.vr_autoplay_taps = {prog:install_write_tap(0xd80010, 0xd80013, "ap_fifo", function(offset, data, mask)
  if offset == 0xd80010 then fifo_lo = data & 0xffff
  elseif offset == 0xd80012 and fifo_lo then
    local w = ((data & 0xffff) << 16) | fifo_lo; fifo_lo = nil
    -- the course load sends 0x0680 <slot>: the race starts there (the attract demo sends it too, before the coin)
    if fifo_want then fifo_want = false; if frame > 800 and not race_start then race_start = frame end
    elseif w == 0x06800000 then fifo_want = true end
    for _, fn in ipairs(fifo_listeners) do fn(w, frame) end
  end
end)}

if os.getenv("VR_DLIST_LOG") and lua_dir then dofile(lua_dir .. "/dlist_log.lua") end
if os.getenv("VR_TRACE_LOG") and lua_dir then dofile(lua_dir .. "/memtrace.lua") end
if os.getenv("VR_RATE_LOG") and lua_dir then dofile(lua_dir .. "/renderrate.lua") end
if os.getenv("VR_COLLISION_LOG") and lua_dir then dofile(lua_dir .. "/collision_log.lua") end
if os.getenv("VR_AUTOPILOT") and lua_dir then dofile(lua_dir .. "/autopilot.lua") end
if os.getenv("VR_FIELD_LOG") and lua_dir then dofile(lua_dir .. "/fieldtrace.lua") end
if os.getenv("VR_HUDMAP_LOG") and lua_dir then dofile(lua_dir .. "/hudmap_log.lua") end
if os.getenv("VR_WHEELS_LOG") and lua_dir then dofile(lua_dir .. "/wheels_log.lua") end
if os.getenv("VR_ATTITUDE_LOG") and lua_dir then dofile(lua_dir .. "/attitude_log.lua") end
if os.getenv("VR_SELECT_DIR") and lua_dir then dofile(lua_dir .. "/select_dump.lua") end
-- replay: no inputs (the .inp drives them); count frames, snapshot every VR_SNAP_EVERY frames from VR_SNAP_FROM
local every, from = tonumber(os.getenv("VR_SNAP_EVERY") or "300"), tonumber(os.getenv("VR_SNAP_FROM") or "1500")
emu.register_frame_done(function()
  frame = frame + 1
  if frame >= from and (frame - from) % every == 0 then manager.machine.video:snapshot() end
end)
