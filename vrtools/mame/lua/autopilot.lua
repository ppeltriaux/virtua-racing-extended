-- Autopilot: steer the player along a centreline. Loaded by autoplay.lua when VR_AUTOPILOT names a CSV of
-- "x,z" arcade points (one per line, in lap order, evenly spaced). The player's position comes from the first
-- TGP collision call (0x1b01) of each frame via autoplay's FIFO hook; heading from the last two positions.
-- Wheel = centre + GAIN * (signed angle to a lookahead point); VR_AUTOPILOT_SIGN flips it, VR_AUTOPILOT_GAIN scales.
local pts = {}
for line in io.lines(os.getenv("VR_AUTOPILOT")) do
  local x, z = line:match("^%s*([-%d.eE]+)%s*,%s*([-%d.eE]+)")
  if x then pts[#pts + 1] = {tonumber(x), tonumber(z)} end
end
assert(#pts >= 3, "autopilot: centreline needs points")
local sign = tonumber(os.getenv("VR_AUTOPILOT_SIGN") or "-1")     -- calibrated on the original Big Forest: -1 follows the line
local gain = tonumber(os.getenv("VR_AUTOPILOT_GAIN") or "160")
local lookahead = tonumber(os.getenv("VR_AUTOPILOT_LOOKAHEAD") or "6")       -- points ahead
-- Phase 26 stage 4: VR_AUTOPILOT_AHEAD, how far ahead (points) the nearest-point search looks from the last one (default 40);
-- a reverse pit path passes near another part of itself (Diablo Canyon's lane beside its road loop), where 15 keeps it on its own part
local ahead = tonumber(os.getenv("VR_AUTOPILOT_AHEAD") or "40")
local px, pz, lx, lz = nil, nil, nil, nil                                   -- current and previous player position
local seen_frame = nil
-- the player's position comes from collision_log.lua (_G.vr_player: the five-call cluster), so VR_COLLISION_LOG
-- must be set as well
local function poll_player()
  local p = _G.vr_player
  if p and p.frame ~= seen_frame then
    seen_frame = p.frame
    lx, lz, px, pz = px, pz, p.x, p.z
  end
end
local lift = tonumber(os.getenv("VR_AUTOPILOT_LIFT") or "0.6")              -- |steering angle| (rad) above which the pedal is released
local last_k = 1
local last_ang, last_off, last_speed = 0.0, 0.0, 0.0
local function nearest()
  -- search near the last index first (the car moves forward), fall back to a full scan
  local best, bestd = last_k, math.huge
  local n = #pts
  for d = -10, ahead do
    local k = ((last_k - 1 + d) % n) + 1
    local dx, dz = pts[k][1] - px, pts[k][2] - pz
    local dd = dx * dx + dz * dz
    if dd < bestd then best, bestd = k, dd end
  end
  if bestd > 150 * 150 then
    for k = 1, n do
      local dx, dz = pts[k][1] - px, pts[k][2] - pz
      local dd = dx * dx + dz * dz
      if dd < bestd then best, bestd = k, dd end
    end
  end
  last_k = best
  return best
end
local log = os.getenv("VR_AUTOPILOT_LOG") and assert(io.open(os.getenv("VR_AUTOPILOT_LOG"), "w")) or nil
local frame = 0
_G.vr_autopilot_wheel = function()
  frame = frame + 1
  poll_player()
  if not px then return nil end
  local k = nearest()
  local offx, offz = pts[k][1] - px, pts[k][2] - pz
  last_off = math.sqrt(offx * offx + offz * offz)
  last_speed = lx and math.sqrt((px - lx) ^ 2 + (pz - lz) ^ 2) or 0.0   -- units per probe interval
  local t = pts[((k - 1 + lookahead) % #pts) + 1]
  local hx, hz
  if lx and ((px - lx) ^ 2 + (pz - lz) ^ 2) > 0.25 then hx, hz = px - lx, pz - lz    -- moving: heading from the motion
  else local nxt = pts[(k % #pts) + 1]; hx, hz = nxt[1] - pts[k][1], nxt[2] - pts[k][2] end
  local tx, tz = t[1] - px, t[2] - pz
  local ang = math.atan(hx * tz - hz * tx, hx * tx + hz * tz)              -- + = target to the left of the heading (x right, z up)
  last_ang = ang
  local v = 128 + sign * gain * ang
  if v < 0 then v = 0 elseif v > 255 then v = 255 end
  if log and frame % 4 == 0 then
    log:write(string.format("%d pos %.1f %.1f head %.2f %.2f k %d target %.1f %.1f ang %.3f wheel %d\n", frame, px, pz, hx, hz, k, t[1], t[2], ang, math.floor(v + 0.5)))
    if frame % 100 == 0 then log:flush() end
  end
  return math.floor(v + 0.5)
end
-- pedal: full throttle unless the car is fast and the steering error is large (hairpins), then released so it
-- can turn; at low speed the motion-derived heading is noisy, so the pedal stays down there
local min_speed = tonumber(os.getenv("VR_AUTOPILOT_LIFT_SPEED") or "3")
_G.vr_autopilot_throttle = function()
  if last_speed > min_speed and math.abs(last_ang) > lift then return 0 end
  return 255
end
