-- Weather stage 3: the cover's pictures (tests/test_weather_cover.py; spike 57's look57.lua and spike 68's stop.lua rewritten).
-- Loaded with VR_EXTRA_LUA. Snapshots with the camera matrix each was taken with, in road-point ranges of a moving race or at a
-- camera spot held still. Env:
--   VR_LOOK_LOG      path: "G <frame>" the green; "K <frame> <n> <road point> <m0..m11>" a snapshot (the n-th of the run, from 1)
--                    and the camera matrix 0x501b00 at that frame end; "STOP <frame> <road point>" the stop begun; "STATIC <frame>"
--                    the camera held still, snapshots from here
--   VR_LOOK_SNAP     "a-b,c-d": road-point ranges (the player's +0xa6), a snapshot every VR_LOOK_EVERY frames (2) after the green
--                    while the car is in one, VR_LOOK_MAX at most (2000)
--   VR_LOOK_MODE     "<hex>:<n>": instead of road points, a snapshot every VR_LOOK_EVERY frames while the word at that address (the
--                    cover's mode, weather/cover.py) is n, VR_LOOK_MAX at most
--   VR_LOOK_STOP     "<road point>[:<frames after the green>]": the first time after the green (+300 by default) the car's road
--                    point is in [R, R+8], the pedal is released, the brake held and the wheel centred from then on; once the camera
--                    translation (0x501b24..) has moved less than 0.01 for 20 frames, VR_LOOK_N (300) snapshots, one a frame
--   VR_LOOK_STOP_BOX "x0,x1,z0,z1": instead of a road point, the stop begins the first time after the green (+300) the car's x and z
--                    (+0x1e, +0x26) are inside that box (a spot a few units from a roof's end, where road points are too coarse)
--   VR_LOOK_FROM     "<frame>": instead of a stop, snapshots from that frame, VR_LOOK_N
--   VR_LOOK_PIT      "<hex>": instead, snapshots from the first frame after the green at whose end the player's handler (+0xa) is
--                    that (runner.PIT_HANDLER: a pit stop, where the pit camera pans), VR_LOOK_N
-- Frames count from 1 at the first frame end (autoplay.lua's).
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local video = manager.machine.video
local log = assert(io.open(assert(os.getenv("VR_LOOK_LOG"), "cover_look.lua: VR_LOOK_LOG is not set"), "w"))
local ranges = {}
for a, b in string.gmatch(os.getenv("VR_LOOK_SNAP") or "", "(%-?%d+)%-(%-?%d+)") do ranges[#ranges + 1] = {tonumber(a), tonumber(b)} end
local every = tonumber(os.getenv("VR_LOOK_EVERY") or "2")
local mode_at, mode_is = string.match(os.getenv("VR_LOOK_MODE") or "", "^(%x+):(%d+)$")
mode_at, mode_is = tonumber(mode_at or "", 16), tonumber(mode_is or "")
local maxn = tonumber(os.getenv("VR_LOOK_MAX") or "2000")
local stop_rp, stop_after = string.match(os.getenv("VR_LOOK_STOP") or "", "^(%-?%d+):?(%d*)$")
stop_rp = tonumber(stop_rp)
stop_after = tonumber(stop_after ~= nil and stop_after ~= "" and stop_after or "300")
local box = {}
for v in string.gmatch(os.getenv("VR_LOOK_STOP_BOX") or "", "[-%d.]+") do box[#box + 1] = tonumber(v) end
local from = tonumber(os.getenv("VR_LOOK_FROM") or "")
local pit = tonumber(os.getenv("VR_LOOK_PIT") or "", 16)
local N = tonumber(os.getenv("VR_LOOK_N") or "300")
local function field(tag, name)
  local port = manager.machine.ioport.ports[tag]
  if not port then return nil end
  for n, f in pairs(port.fields) do if n == name then return f end end
  return nil
end
local accel, brake, wheel = field(":ACCEL", "P1 Pedal 1"), field(":BRAKE", "P1 Pedal 2"), field(":WHEEL", "Paddle")
local frame, loaded, green, stopping, still, snapping, nsnap, last = 0, false, nil, false, 0, false, 0, nil
local function f32(a) return (string.unpack("<f", string.pack("<I4", mem:read_u32(a)))) end
local function s16(a) local v = mem:read_u16(a); return v >= 0x8000 and v - 0x10000 or v end
local function snap(rp)
  video:snapshot(); nsnap = nsnap + 1
  local m = {}
  for k = 0, 11 do m[#m + 1] = string.format("%.5f", f32(0x501b00 + 4 * k)) end
  log:write(string.format("K %d %d %d %s\n", frame, nsnap, rp, table.concat(m, " ")))
  if nsnap % 50 == 0 then log:flush() end
end
local first = true
emu.register_frame_done(function()
  if first then
    first = false
    emu.register_frame_done(function()            -- registered after autoplay's own: its inputs are overridden once stopping
      if stopping then
        if accel then accel:set_value(0) end
        if brake then brake:set_value(255) end
        if wheel then wheel:set_value(128) end
      end
    end)
  end
  frame = frame + 1
  local mode = mem:read_u8(0x501138)
  if mode == 0x11 then loaded = true end
  if loaded and not green and mode == 0x14 then green = frame; log:write(string.format("G %d\n", frame)) end
  local rp = s16(0x400d00 + 0xa6)
  if pit and green and not from and mem:read_u32(0x400d00 + 0xa) == pit then
    from = frame; log:write(string.format("PIT %d %d\n", frame, rp))
  end
  if #box == 4 and green and not stopping and frame > green + stop_after then
    local x, z = f32(0x400d00 + 0x1e), f32(0x400d00 + 0x26)
    if x >= box[1] and x <= box[2] and z >= box[3] and z <= box[4] then
      stopping = true; log:write(string.format("STOP %d %d\n", frame, rp)); log:flush()
    end
  end
  if stop_rp and green and not stopping and frame > green + stop_after and rp >= stop_rp and rp <= stop_rp + 8 then
    stopping = true; log:write(string.format("STOP %d %d\n", frame, rp)); log:flush()
  end
  if (stopping or (from and frame >= from)) and nsnap < N then
    local t = {f32(0x501b24), f32(0x501b28), f32(0x501b2c)}
    if last and math.abs(t[1] - last[1]) + math.abs(t[2] - last[2]) + math.abs(t[3] - last[3]) < 0.01 then still = still + 1 else still = 0 end
    last = t
    if not snapping and (from or still >= 20) then snapping = true; log:write(string.format("STATIC %d\n", frame)) end
    if snapping then snap(rp) end
    return
  end
  if green and mode_at and nsnap < maxn and frame % every == 0 and mem:read_u32(mode_at) == mode_is then snap(rp); return end
  if green and #ranges > 0 and nsnap < maxn and frame % every == 0 then
    for _, r in ipairs(ranges) do
      if rp >= r[1] and rp <= r[2] then snap(rp); break end
    end
  end
end)
emu.add_machine_stop_notifier(function() log:close() end)
