-- Coin up, pick a course with the wheel, floor the gas. Env: VR_COURSE (0/1/2), VR_WHEEL (paddle 0..255 overrides), VR_MANUAL ("1").
-- If VR_DLIST_LOG is set, also runs dlist_log.lua from VR_LUA_DIR.
local course = tonumber(os.getenv("VR_COURSE") or "0")
local manual = os.getenv("VR_MANUAL") == "1"
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

local function field(tag, name)
  local port = manager.machine.ioport.ports[tag]
  for fname, f in pairs(port.fields) do
    if fname == name then return f end
  end
  error("no field " .. name .. " on " .. tag)
end

local coin  = field(":IN.0", "Coin 1")
local start = field(":IN.0", "1 Player Start")
local wheel = field(":WHEEL", "Paddle")
local accel = field(":ACCEL", "P1 Pedal 1")
-- select-screen zones (measured): <=150 Big Forest, ~175 Bay Bridge, >=200 Acropolis; centre (128) = Big Forest
local wheel_pos = tonumber(os.getenv("VR_WHEEL")) or ({[0] = 0, [1] = 175, [2] = 255})[course] or 0   -- VR_WHEEL: absolute paddle value
-- VR_WHEEL_FROM: the frame from which the paddle is held. Just after START is released: the game takes the paddle
-- read around coin/START as the steering centre (a hold from boot biased the whole race), and the filtered value
-- needs ~50 frames before the earliest course latch
local wheel_from = tonumber(os.getenv("VR_WHEEL_FROM") or "735")
-- VR_WHEEL_SWEEP="from:to:frames": from VR_WHEEL_FROM the paddle moves linearly from `from` to `to` over `frames`
-- frames, then holds `to` (films the select row scrolling). START is pressed at VR_START_AT (default 720): keep it
-- before the sweep, the game samples the paddle around coin/START as the steering centre and a START with the wheel
-- away from centre biases the whole race. Without a sweep the paddle holds VR_WHEEL as before.
local sweep = nil
do
  local a, b, n = string.match(os.getenv("VR_WHEEL_SWEEP") or "", "(%d+):(%d+):(%d+)")
  if a then sweep = {from = tonumber(a), to = tonumber(b), frames = tonumber(n)}; wheel_pos = sweep.to end
end
local start_at = tonumber(os.getenv("VR_START_AT") or "720")
local pokes = {}                                                -- VR_POKE="40dca1=2,...": bytes written every frame before the coin (operator settings)
for a, v in string.gmatch(os.getenv("VR_POKE") or "", "(%x+)=(%d+)") do pokes[#pokes + 1] = {tonumber(a, 16), tonumber(v)} end
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local snaps = {}                                              -- VR_SNAPS="1300,2400" (default) : frames to snapshot
for f in string.gmatch(os.getenv("VR_SNAPS") or "1300,2400", "%d+") do snaps[tonumber(f)] = true end
local snaps_after = {}                                        -- VR_SNAPS_AFTER_START="300,600": frames after the detected race start
for f in string.gmatch(os.getenv("VR_SNAPS_AFTER_START") or "", "%d+") do snaps_after[tonumber(f)] = true end

-- The race start is detected, not timed: the frame the course loads at varies between MAME invocations
-- (865..1605 seen). The wheel is held at the select position until then and centred one frame later.
emu.register_frame_done(function()
  frame = frame + 1
  if frame < 600 then for _, p in ipairs(pokes) do mem:write_u8(p[1], p[2]) end end
  if frame == 600 then coin:set_value(1) elseif frame == 610 then coin:set_value(0) end
  if frame == start_at then start:set_value(1) elseif frame == start_at + 10 then start:set_value(0) end
  if frame >= wheel_from and not race_start then                                   -- held from VR_WHEEL_FROM: the filtered wheel value needs ~50 frames, START can then confirm the choice
    local v = wheel_pos
    if sweep then
      local t = math.min(1, (frame - wheel_from) / sweep.frames)
      v = math.floor(sweep.from + (sweep.to - sweep.from) * t + 0.5)
    end
    wheel:set_value(v)
  end
  if race_start and frame == race_start + 1 then wheel:set_value(128) end
  -- VR_RACE_WHEEL: a paddle value held from the race start (an experiment's constant steer; the autopilot overrides it)
  if race_start and frame > race_start + 1 and os.getenv("VR_RACE_WHEEL") then wheel:set_value(tonumber(os.getenv("VR_RACE_WHEEL"))) end
  -- VR_RACE_STEER="from:frames:value": from race_start+from, the paddle holds `value` for `frames` frames, then centres
  if race_start and os.getenv("VR_RACE_STEER") then
    local a, n, v = string.match(os.getenv("VR_RACE_STEER"), "(%d+):(%d+):(%d+)")
    local t = frame - race_start
    if t >= tonumber(a) and t < tonumber(a) + tonumber(n) then wheel:set_value(tonumber(v)) elseif t == tonumber(a) + tonumber(n) then wheel:set_value(128) end
  end
  if race_start and frame > race_start + 1 and type(_G.vr_autopilot_wheel) == "function" then
    local v = _G.vr_autopilot_wheel()
    if v then wheel:set_value(v) end
  end
  if snaps[frame] or (race_start and snaps_after[frame - race_start]) then manager.machine.video:snapshot() end
  if frame >= 1400 or (race_start and frame > race_start) then      -- floor the pedal from the race start (or 1400 at the latest)
    local throttle = 255
    if race_start and type(_G.vr_autopilot_throttle) == "function" then throttle = _G.vr_autopilot_throttle() end   -- the autopilot lifts in hairpins
    accel:set_value(throttle)
    if manual then start:set_value(1) end
  end
end)
-- VR_EXTRA_LUA: another script to run alongside (experiments)
if os.getenv("VR_EXTRA_LUA") then dofile(os.getenv("VR_EXTRA_LUA")) end
