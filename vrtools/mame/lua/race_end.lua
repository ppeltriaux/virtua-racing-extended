-- Phase 26 stage 3 (Task 1): a one-lap race with the clock held, and what follows it: the record, the attract, a second game.
-- Loaded with VR_EXTRA_LUA alongside autoplay.lua (its frame callback runs after autoplay's and direction.lua's). Env:
--   VR_END_LOG    the log (required)
--   VR_END_TABLE  "lo-hi[,lo-hi...]" (hex): write taps on those RAM ranges (a ranking table; Phase 27: the battery RAM) from the
--                 race load on
--   VR_END_READS  "lo-hi" (hex, Phase 27): a read tap on that range (the last-entry offset cell the insert adds), installed with
--                 the write taps
--   VR_END_TAP_AT n (Phase 27): the taps are installed at frame n instead of at the race load (600: the coin, after autoplay.lua's
--                 VR_POKE has written its last frame)
--   VR_END_COIN   n: a coin, then START, once the n-th attract pit scene (mode 0x07) after the race has ended (none when unset)
--   VR_END_NEXT   "wheel:direction[:rain][;wheel:direction[:rain]...]" (Phase 27; weather stage 2 the third field and the list:
--                 each item one more game after the one before, the same way): a second game in the same session, driven here from NEXT_COIN frames after the first
--                 game's attract load (mode 0x02): its coin, START and course select on autoplay.lua's frames counted from that coin
--                 as from autoplay's coin at 600 (the wheel at 128 around the coin and START, the paddle `wheel` from 735, the
--                 course's gas press at DIR_PRESS, the COURSE DIRECTION screen answered as autoplay answers it: REVERSE when
--                 `direction` is 1, else NORMAL, the second press at 1400); its race is held as the first (its own L line) and
--                 these inputs end at its load, where autoplay.lua and the autopilot drive again. Weather stage 1: on a set with the
--                 COURSE WEATHER screen (VR_WEATHER_SELECT / VR_WEATHER_WORD, as autoplay.lua tells it) the screens are answered as
--                 autoplay answers them there (REVERSE from 1260, the direction pressed at 1300, the wheel back to 128 at 1310: DRY,
--                 the press from 1400 locks the weather), so the second race loads on the frame it does without the screen; with
--                 the third field 1 the wheel goes to 200 (RAIN) from 1360 to the weather's lock, as autoplay.lua's VR_RAIN=1
--   VR_END_NEXT_LINE  the second race's autopilot line (a centreline CSV), handed to autopilot.lua's `vr_autopilot_load` at its load
--   VR_END_PRESET "table:d,d,...[;table:d,...]" (hex table, signed decimal d, Phase 27 Task 4): at each race's results (the first
--                 frame end the mode byte reads 0x16 after the race: the race's time is final; the insert ran three frames later in
--                 every Phase 27 Task 4 run, on the frame end mode 0x1b is first read or the next) the n entries from each `table` (n = the number of d) are written
--                 through MAME's nvram share (no W line): entry k = rank k + 1, the race's time [0x501168] + d_k at +4 and +0x10, 0 at
--                 +8 (the view), -1 at +0xc, the name 'A' + k three times and a NUL at +0x14; each table is then read back through
--                 the CPU's bus (a P line). So a table can be preset round a time that is only known once the race has run
--   VR_END_SNAP   n (Phase 27 Task 4): a snapshot (MAME's snapshot directory) n frames after each name entry starts (the first frame
--                 end the mode byte reads 0x1e after a race)
--   VR_DIRECTION_RAM  the flag's address (hex, course.DIRECTION_RAM; required)
-- The race load is the first frame end the next-mode byte 0x501139 reads 0x11. From then until the race ends (the first mode
-- outside 0x11..0x14 after it) this writes 1 to the lap count 0x5011a4 in modes 0x12-0x14, and in mode 0x14 the race clock
-- 0x50116c back to 1920 whenever it is below 600, so the car finishes the lap before the clock runs out. Lines:
--   L <frame>                                                      the race load (VR_END_NEXT: one for each race)
--   M <frame> <mode 0x501139> <state 0x501180> <flag> <record 0x5018fc> <handler>
--       every frame end at which one of them changes (hex but the frame and the state); the handler is the select entity's
--       ([0x501318] + 0xa) while the mode byte reads 0x10, else 0
--   W <frame> <pc> <address> <data> <mask>                         a write into VR_END_TABLE (hex but the frame; the bus is 16 bits
--                                                                  wide: the address is even, the mask names the bytes written)
--   R <frame> <pc> <address> <data> <mask>                         a read in VR_END_READS (likewise)
--   C <frame>                                                      the coin (VR_END_COIN, VR_END_NEXT)
--   T <frame> <time>                                               each race's time [0x501168] (1/32 s, decimal) at its results
--                                                                  (the frame end VR_END_PRESET writes at; logged with or without it)
--   P <frame> <table> <hexbytes>                                   a VR_END_PRESET table read back through the bus after the write
--   S <frame>                                                      a snapshot (VR_END_SNAP)
-- Frames are counted from 1 at the first frame end, as autoplay.lua counts them.
local out = assert(io.open(assert(os.getenv("VR_END_LOG"), "race_end.lua: VR_END_LOG is not set"), "w"))
local cpu = manager.machine.devices[":maincpu"]
local mem = cpu.spaces["program"]
local function field(tag, name)
  local port = manager.machine.ioport.ports[tag]
  if not port then error("race_end.lua: no port " .. tag) end
  for n, f in pairs(port.fields) do if n == name then return f end end
  error("race_end.lua: no field " .. name .. " on " .. tag)
end
local coin, start = field(":IN.0", "Coin 1"), field(":IN.0", "1 Player Start")
local ranges = {}
for lo, hi in string.gmatch(os.getenv("VR_END_TABLE") or "", "(%x+)-(%x+)") do ranges[#ranges + 1] = {tonumber(lo, 16), tonumber(hi, 16)} end
local rlo, rhi = string.match(os.getenv("VR_END_READS") or "", "(%x+)-(%x+)")
local tap_at = tonumber(os.getenv("VR_END_TAP_AT") or "")
local coin_after = tonumber(os.getenv("VR_END_COIN") or "")
local flag_at = tonumber(os.getenv("VR_DIRECTION_RAM") or "", 16)
if not flag_at then error("race_end.lua: VR_DIRECTION_RAM is missing or not hex: " .. tostring(os.getenv("VR_DIRECTION_RAM"))) end
local next_games = {}                       -- next_games[k]: the game after race k (wheel, reverse, rain)
for item in string.gmatch(os.getenv("VR_END_NEXT") or "", "[^;]+") do
  local w, d, r = string.match(item, "^(%d+):([01])$")                -- wheel:direction, or wheel:direction:rain (the ":" required)
  if not w then w, d, r = string.match(item, "^(%d+):([01]):([01])$") end
  if not w then error("race_end.lua: VR_END_NEXT is not wheel:direction[:rain][;...]: " .. os.getenv("VR_END_NEXT")) end
  next_games[#next_games + 1] = {tonumber(w), d == "1", r == "1"}
end
local next_line = os.getenv("VR_END_NEXT_LINE")
local wx_at, wx_word = tonumber(os.getenv("VR_WEATHER_SELECT") or "", 16), tonumber(os.getenv("VR_WEATHER_WORD") or "", 16)
local weather = wx_at ~= nil and wx_word ~= nil and mem:read_u32(wx_at) == wx_word
local presets = {}
for t, ds in string.gmatch(os.getenv("VR_END_PRESET") or "", "(%x+):([-%d,]+)") do
  local d = {}
  for x in string.gmatch(ds, "-?%d+") do d[#d + 1] = tonumber(x) end
  presets[#presets + 1] = {tonumber(t, 16), d}
end
if os.getenv("VR_END_PRESET") and #presets == 0 then
  error("race_end.lua: VR_END_PRESET is not table:d,...: " .. os.getenv("VR_END_PRESET"))
end
local snap_after = tonumber(os.getenv("VR_END_SNAP") or "")
local nvram = manager.machine.memory.shares[":nvram"]
local results, names, snap_at = 0, 0, nil   -- the races whose results (mode 0x16) and name entry (mode 0x1e) have been seen
local NEXT_COIN = 60                        -- frames from the first game's attract load to the second game's coin
local wheel, accel = field(":WHEEL", "Paddle"), field(":ACCEL", "P1 Pedal 1")
local frame, load, racing, last, scenes, in_scene, coin_at = 0, nil, false, "", 0, false, nil
local races, attract_at, next_at = 0, nil, nil
_G.vr_race_end_taps = {}

local function install_taps()
  if #_G.vr_race_end_taps > 0 then return end
  for k, r in ipairs(ranges) do
    _G.vr_race_end_taps[#_G.vr_race_end_taps + 1] = mem:install_write_tap(r[1], r[2], "race_end_table" .. k, function(offset, data, mask)
      out:write(string.format("W %d %x %x %x %x\n", frame, cpu.state["PC"].value, offset, data, mask))
    end)
  end
  if rlo then
    _G.vr_race_end_taps[#_G.vr_race_end_taps + 1] = mem:install_read_tap(tonumber(rlo, 16), tonumber(rhi, 16), "race_end_reads", function(offset, data, mask)
      out:write(string.format("R %d %x %x %x %x\n", frame, cpu.state["PC"].value, offset, data, mask))
    end)
  end
end

emu.register_frame_done(function()
  frame = frame + 1
  local mode = mem:read_u8(0x501139)
  if tap_at and frame == tap_at then install_taps() end
  if mode == 0x11 and not racing and (races == 0 or (next_games[races] and next_at)) then   -- a race load (the first; VR_END_NEXT's)
    races, racing = races + 1, true
    attract_at, next_at = nil, nil
    load = load or frame
    out:write(string.format("L %d\n", frame))
    if not tap_at then install_taps() end
    if races == 2 and next_line then
      if type(_G.vr_autopilot_load) ~= "function" then error("race_end.lua: VR_END_NEXT_LINE without autopilot.lua (VR_AUTOPILOT)") end
      _G.vr_autopilot_load(next_line)
    end
  end
  if racing then
    if mode < 0x11 or mode > 0x14 then racing = false
    elseif mode >= 0x12 then
      mem:write_u8(0x5011A4, 1)
      if mode == 0x14 and mem:read_i32(0x50116C) < 600 then mem:write_u32(0x50116C, 1920) end
    end
  end
  if not racing and races > results and mode == 0x16 then             -- a race's results: its time is final, the insert 3 frames on
    results = races
    local time = mem:read_i32(0x501168)
    out:write(string.format("T %d %d\n", frame, time))
    for _, p in ipairs(presets) do
      local base = p[1] - 0x400000
      for k, d in ipairs(p[2]) do
        local letter = 0x40 + k
        local words = {k, time + d, 0, -1, time + d, letter | letter << 8 | letter << 16}
        for w, v in ipairs(words) do                                 -- little-endian bytes (the V60's order)
          for j = 0, 3 do nvram:write_u8(base + 24 * (k - 1) + 4 * (w - 1) + j, (v >> 8 * j) & 0xFF) end
        end
      end
      local back = {}
      for j = 0, 24 * #p[2] - 1 do back[#back + 1] = string.format("%02x", mem:read_u8(p[1] + j)) end
      out:write(string.format("P %d %x %s\n", frame, p[1], table.concat(back)))
    end
  end
  if not racing and races > names and mode == 0x1E then              -- a name entry starts
    names = races
    if snap_after then snap_at = frame + snap_after end
  end
  if snap_at and frame == snap_at then manager.machine.video:snapshot(); out:write(string.format("S %d\n", frame)); snap_at = nil end
  local handler = 0
  if mode == 0x10 then
    local e = mem:read_u32(0x501318)
    if e >= 0x400000 and e < 0x600000 then handler = mem:read_u32(e + 0xA) end
  end
  local s = string.format("%02x %d %02x %x %x", mode, mem:read_u8(0x501180), mem:read_u8(flag_at), mem:read_u32(0x5018FC), handler)
  if s ~= last then out:write(string.format("M %d %s\n", frame, s)); last = s end
  if load and not racing and coin_after and not coin_at then                -- the attract's pit scenes after the race
    if mode == 0x07 then in_scene = true
    elseif in_scene then
      in_scene, scenes = false, scenes + 1
      if scenes == coin_after then coin_at = frame + 1 end
    end
  end
  if coin_at then
    local t = frame - coin_at
    if t == 0 then coin:set_value(1); out:write(string.format("C %d\n", frame)) elseif t == 10 then coin:set_value(0)
    elseif t == 40 then start:set_value(1) elseif t == 50 then start:set_value(0) end
  end
  if races >= 1 and next_games[races] and not racing and not attract_at and mode == 0x02 then attract_at = frame end
  if attract_at and not next_at and frame == attract_at + NEXT_COIN then next_at = frame; out:write(string.format("C %d\n", frame)) end
  if next_at and races >= 1 and next_games[races] then -- the next game up to its race load, on autoplay.lua's frames (coin at 600)
    local next_wheel, next_reverse, next_rain = table.unpack(next_games[races])
    local t = frame - next_at + 600
    coin:set_value((t < 610) and 1 or 0)
    start:set_value((t >= 720 and t < 730) and 1 or 0)
    local w, gas = (t < 735) and 128 or next_wheel, 0
    if (t >= 1200 and t < 1210) or t >= 1400 then gas = 255 end                 -- DIR_PRESS..DIR_LIFT, the second press from 1400
    if t >= 1210 and t < 1402 then w = (next_reverse and t >= 1300) and 200 or 128 end     -- DIR_LIFT, DIR_STEER, DIR_RETURN
    if weather then                                                             -- the direction at 1300, the weather (DRY) at 1400
      if t >= 1300 and t < 1310 then gas = 255 end
      if t >= 1210 and t < 1402 then w = (next_reverse and t >= 1260 and t < 1310) and 200 or 128 end
      if next_rain and t >= 1360 and t < 1402 then w = 200 end                  -- weather stage 2: RAIN, as autoplay's W_RAIN
    end
    wheel:set_value(w); accel:set_value(gas)
  end
  out:flush()
end)
