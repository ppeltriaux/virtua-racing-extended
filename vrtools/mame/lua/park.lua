-- Phase 90 fix round 1 (I4): the car parked on the road at given road points, facing along it, for the rain's room with a
-- stopped car (tests/test_pack_rate.py's parked check). Loaded with VR_EXTRA_LUA beside autoplay.lua's autopilot. Env:
--   VR_PARK         "r1,r2,...": road points (the player's +0xa6, in the race's own numbering); each taken once, in the order the
--                   car meets them: from APPROACH points before it the pedal is released and the brake held; stopped short of it,
--                   the car creeps on (pedal CREEP) to within NEAR points; there the brake is held, the wheel centred, and once the car has moved
--                   less than 0.01 a frame for 20 frames it is held still VR_PARK_FRAMES frames (240); then the autopilot goes on
--   VR_PARK_N       the lap's road points (to count "ahead" across the line)
--   VR_PARK_LOG     path: "G <frame>" the green; "PARK <road point asked> <road point held> <first still frame> <last frame>"
-- Frames count from 1 at the first frame end (autoplay.lua's and frame_rate.lua's count).
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local log = assert(io.open(assert(os.getenv("VR_PARK_LOG"), "park.lua: VR_PARK_LOG is not set"), "w"))
local places = {}
for v in string.gmatch(os.getenv("VR_PARK") or "", "%-?%d+") do places[#places + 1] = {rp = tonumber(v), done = false} end
local n = assert(tonumber(os.getenv("VR_PARK_N") or ""), "park.lua: VR_PARK_N is not set")
local hold_frames = tonumber(os.getenv("VR_PARK_FRAMES") or "240")
local APPROACH, CREEP, NEAR = 30, 255, 3                -- brake from 30 points before; creep at full gas to within 3
local function field(tag, name)
  local port = manager.machine.ioport.ports[tag]
  if not port then return nil end
  for k, f in pairs(port.fields) do if k == name then return f end end
  return nil
end
local accel, brake, wheel = field(":ACCEL", "P1 Pedal 1"), field(":BRAKE", "P1 Pedal 2"), field(":WHEEL", "Paddle")
local function f32(a) return (string.unpack("<f", string.pack("<I4", mem:read_u32(a)))) end
local function s16(a) local v = mem:read_u16(a); return v >= 0x8000 and v - 0x10000 or v end
local frame, loaded, green = 0, false, nil
local cur, phase, still, from, lx, lz, last_rp, dirn = nil, nil, 0, nil, nil, nil, nil, 1
local first = true
emu.register_frame_done(function()
  if first then
    first = false
    emu.register_frame_done(function()                  -- registered after autoplay's own: its inputs are overridden while parking
      if phase == "brake" or phase == "hold" then
        if accel then accel:set_value(0) end
        if brake then brake:set_value(255) end
        if wheel and phase == "hold" then wheel:set_value(128) end
      elseif phase == "creep" then
        if accel then accel:set_value(CREEP) end
        if brake then brake:set_value(0) end
      elseif brake then brake:set_value(0) end
    end)
  end
  frame = frame + 1
  local mode = mem:read_u8(0x501138)
  if mode == 0x11 then loaded = true end
  if loaded and not green and mode == 0x14 then green = frame; log:write(string.format("G %d\n", frame)); log:flush() end
  if not green then return end
  local rp = s16(0x400d00 + 0xa6)
  local x, z = f32(0x400d00 + 0x1e), f32(0x400d00 + 0x26)
  local moved = lx and math.sqrt((x - lx) ^ 2 + (z - lz) ^ 2) or 1.0
  lx, lz = x, z
  if last_rp and rp ~= last_rp then                     -- the way the road points run in this race
    local d = (rp - last_rp) % n
    if d < n / 2 then dirn = 1 elseif n - d < n / 2 then dirn = -1 end
  end
  last_rp = rp
  if not cur then
    for _, p in ipairs(places) do
      if not p.done and ((p.rp - rp) * dirn) % n <= APPROACH and frame > green + 120 then cur, phase = p, "brake"; break end
    end
    return
  end
  local ahead = ((cur.rp - rp) * dirn) % n
  local short = ahead > 0 and ahead < n / 2
  if phase == "brake" and moved < 0.05 then phase = (short and ahead > NEAR) and "creep" or "hold"; still = 0 end
  if phase == "creep" and (not short or ahead <= NEAR) then phase = "brake" end
  if phase == "hold" then
    if moved < 0.01 then still = still + 1 else still = 0 end
    if still == 20 and not from then from = frame end
    if from and frame >= from + hold_frames then
      log:write(string.format("PARK %d %d %d %d\n", cur.rp, rp, from, frame)); log:flush()
      cur.done, cur, phase, from = true, nil, nil, nil
    end
  end
end)
