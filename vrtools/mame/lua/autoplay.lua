-- Coin up, pick a course with the wheel, floor the gas. Env: VR_COURSE (0/1/2), VR_WHEEL (paddle 0..255 overrides), VR_MANUAL ("1").
-- If VR_DLIST_LOG is set, also runs dlist_log.lua from VR_LUA_DIR.
-- Phase 26 stage 3 (plan D14): on a course with a reverse variant the course lock opens the COURSE DIRECTION screen
-- (dirscreen.py), and this answers it: the course's gas press comes early (DIR_PRESS), the pedal is lifted (DIR_LIFT), the wheel
-- goes to 128 (on the screen's NORMAL side, which also arms the wheel: plan D6) and, with VR_DIRECTION=1, to 200 (REVERSE) from
-- DIR_STEER, and the gas floored at 1400 as before is the second press: its edge at frame 1402 locks the screen on the frame the
-- course select locked on before the screen existed, so the race loads on the same frame; the paddle returns to the course's
-- value at DIR_RETURN, right after that lock, as it was held there before. START is held from DIR_PRESS with VR_MANUAL=1, so the
-- course select latches the manual transmission (0x501936) at the early lock as it did at 1402. The screen is answered only when
-- it will open: at DIR_PRESS the course select's handler (0xfc26c5) runs, the boot ROM's course lock site calls `dirlock`
-- (0xfc2788 holds a `jsr`), the cabinet is not linked ([0x40dc8c] 0) and the chosen entry ([0x501940]) has a word in the reverse
-- table (VR_REVERSE_TABLE, hex: the runner passes directory_layout()["reverse"]). VR_DIR_ANSWER=0: never answered (the gas
-- floored at 1400 and held: the screen waits for its countdown, a held pedal never confirms). VR_DIRECTION_FORCE=1 loads
-- direction.lua, which holds the flag at VR_DIRECTION on every select-screen frame (for a course no screen serves). With
-- VR_DIRECTION=1 on entries 3-9 of a set with the screen and without VR_DIRECTION_FORCE, a screen that will not be answered
-- is an error naming why (it would race in the normal direction). A VR_WHEEL_SWEEP still moving at DIR_PRESS (VR_WHEEL_FROM +
-- its frames > DIR_PRESS) is such a reason: the early press would lock whatever entry the sweep is passing, so on that run the
-- screen is not answered (the gas floored at 1400 locks the course as before the screen existed; a screen that opens is left to
-- its countdown) and one line on stderr says so.
local course = tonumber(os.getenv("VR_COURSE") or "0")
local manual = os.getenv("VR_MANUAL") == "1"
local lua_dir = os.getenv("VR_LUA_DIR")
-- The answer's frames. DIR_PRESS: after the course select's countdown has passed 0x180 (frame ~1126: its voice cue at 0x180 fires
-- as before), and early enough that the screen (open from DIR_PRESS + 4) has ~200 frames for the wheel before 1402, its own
-- countdown (575 frames) ending long after. DIR_LIFT: the course press's edge (DIR_PRESS + 2) has been seen; the pedal stays below
-- 128 until 1400, so the press at 1400 is a new edge. DIR_STEER: 128 from DIR_LIFT, 200 from DIR_STEER (~100 frames each for the
-- wheel: measured, the screen saw R10 <= 0x1c 4 frames after the paddle went to 128 and > 0x1c 2 frames after 200). DIR_RETURN: the lock's frame (its logic frame read the wheel before this
-- frame end), so the wheel is back at the course's value from 1402 on as it was before.
local DIR_PRESS, DIR_LIFT, DIR_STEER, DIR_RETURN = 1200, 1210, 1300, 1402
local dir_answer = os.getenv("VR_DIR_ANSWER") ~= "0"
local dir_reverse = os.getenv("VR_DIRECTION") == "1"
local dir_table = tonumber(os.getenv("VR_REVERSE_TABLE") or "", 16)
local dir_force = os.getenv("VR_DIRECTION_FORCE") == "1"
-- VR_DIR_START_OFF=1 (a test switch, with VR_MANUAL=1): START is released from DIR_LIFT while the screen is up, until the race
-- load, so that a re-latch of the transmission on the screen would show (the course select latched it at the early press).
local start_off = os.getenv("VR_DIR_START_OFF") == "1"
local answering = false

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
if os.getenv("VR_DIRECTION_FORCE") == "1" and lua_dir then dofile(lua_dir .. "/direction.lua") end
if os.getenv("VR_RACE_LOG") and lua_dir then dofile(lua_dir .. "/race_log.lua") end
if os.getenv("VR_START_LOG") and lua_dir then dofile(lua_dir .. "/start_log.lua") end
if os.getenv("VR_FIGURES_LOG") and lua_dir then dofile(lua_dir .. "/figures_log.lua") end
if os.getenv("VR_EDGES_LOG") and lua_dir then dofile(lua_dir .. "/edges_log.lua") end
if os.getenv("VR_SELECT_DIR") and lua_dir then dofile(lua_dir .. "/select_dump.lua") end
if os.getenv("VR_DIR_LOG") and lua_dir then dofile(lua_dir .. "/dirscreen_log.lua") end
if os.getenv("VR_HUD_LOG") and lua_dir then dofile(lua_dir .. "/hud_log.lua") end         -- stage 3 Task 6: the HUD name's cells
if os.getenv("VR_SLOT_LOG") and lua_dir then dofile(lua_dir .. "/slot_log.lua") end       -- stage 3 Task 7: the middle slot on screen
if os.getenv("VR_PIT_LOG") and lua_dir then dofile(lua_dir .. "/pit_log.lua") end         -- stage 4 Task 4: the pit stop and its crew
if os.getenv("VR_CREW_DRAW_LOG") and lua_dir then dofile(lua_dir .. "/crewdraw_log.lua") end   -- stage 4 Task 5: the crew's mirrored pushes

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
local sweep_late = sweep ~= nil and wheel_from + sweep.frames > DIR_PRESS   -- the sweep still moving at DIR_PRESS: no early press (top)
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
  if frame == DIR_PRESS and dir_answer and mem:read_u8(0xFC2788) == 0xE8 then     -- the set has the screen: will it open (see the top)?
    local entry, e = mem:read_u8(0x501940), mem:read_u32(0x501318)
    local why = nil
    if sweep_late then why = string.format("the wheel sweep (VR_WHEEL_FROM %d + %d frames) is still moving at frame %d", wheel_from, sweep.frames, DIR_PRESS)
    elseif not dir_table then why = "VR_REVERSE_TABLE is not set"
    elseif mem:read_u8(0x501139) ~= 0x10 then why = string.format("the mode is %02x, not the select screen's 10", mem:read_u8(0x501139))
    elseif mem:read_u8(0x40DC8C) ~= 0 then why = "linked play ([0x40dc8c] is not 0)"
    elseif not (e >= 0x400000 and e < 0x600000 and mem:read_u32(e + 0xA) == 0xFC26C5) then
      why = string.format("the select entity's handler is %x, not the course select's fc26c5", (e >= 0x400000 and e < 0x600000) and mem:read_u32(e + 0xA) or 0)
    elseif mem:read_u32(dir_table + 4 * entry) == 0 then why = string.format("entry %d's word in the reverse table (%x) is 0", entry, dir_table)
    end
    answering = why == nil
    -- VR_DIRECTION=1 asks for a reverse race: on a converted entry of a set with the screen, not answering would race normal
    -- (with a sweep still moving the entry read here is the one it is passing, not the one it will choose: any entry counts)
    if why and dir_reverse and not dir_force and (sweep_late or (entry >= 3 and entry <= 9)) then
      -- an error() inside a frame callback is only logged by MAME ("[LUA ERROR] in execute_function") and the run goes on, so
      -- the message goes to stderr and MAME is ended with a failure status (run_mame raises MameError with the message)
      io.stderr:write(string.format("autoplay.lua: VR_DIRECTION=1 but the COURSE DIRECTION screen will not be answered on entry %d at frame %d: %s\n", entry, frame, why))
      io.stderr:flush()
      os.exit(3)
    end
    if sweep_late then
      io.stderr:write(string.format("autoplay.lua: the COURSE DIRECTION screen is not answered: %s; the gas floored at 1400 locks the course and a screen that opens is left to its countdown\n", why))
      io.stderr:flush()
    end
  end
  if frame >= wheel_from and not race_start then                                   -- held from VR_WHEEL_FROM: the filtered wheel value needs ~50 frames, START can then confirm the choice
    local v = wheel_pos
    if sweep then
      local t = math.min(1, (frame - wheel_from) / sweep.frames)
      v = math.floor(sweep.from + (sweep.to - sweep.from) * t + 0.5)
    end
    if answering and frame >= DIR_LIFT and frame < DIR_RETURN then v = (dir_reverse and frame >= DIR_STEER) and 200 or 128 end
    wheel:set_value(v)
  end
  if answering and frame >= DIR_PRESS and frame < 1400 then                        -- the early course press, then the lift
    accel:set_value(frame < DIR_LIFT and 255 or 0)
    if manual then start:set_value((start_off and frame >= DIR_LIFT) and 0 or 1) end
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
    if manual then start:set_value((start_off and answering and mem:read_u8(0x501139) == 0x10) and 0 or 1) end
  end
end)
-- VR_EXTRA_LUA: another script to run alongside (experiments)
if os.getenv("VR_EXTRA_LUA") then dofile(os.getenv("VR_EXTRA_LUA")) end
