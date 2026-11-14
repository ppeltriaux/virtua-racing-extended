-- Phase 26 stage 3 (Task 2): the pedal and the wheel on the COURSE DIRECTION screen, by hand. Loaded with VR_EXTRA_LUA alongside
-- autoplay.lua (its frame callback runs after autoplay's, so its values win), with VR_DIR_ANSWER=0 so that autoplay does not
-- answer the screen itself. VR_DIR_DRIVE="frame:gas:paddle,...": from each listed frame (counted from 1 at the first frame end,
-- as autoplay counts them) the gas pedal and the paddle hold the given values (0..255), until the next-mode byte 0x501139 reads
-- 0x11 (the race load), from which autoplay drives alone again.
local steps = {}
for f, g, w in string.gmatch(os.getenv("VR_DIR_DRIVE") or "", "(%d+):(%d+):(%d+)") do
  steps[#steps + 1] = {tonumber(f), tonumber(g), tonumber(w)}
end
table.sort(steps, function(a, b) return a[1] < b[1] end)
local function field(tag, name)
  for n, f in pairs(manager.machine.ioport.ports[tag].fields) do if n == name then return f end end
  error("dirscreen_drive.lua: no field " .. name .. " on " .. tag)
end
local accel, wheel = field(":ACCEL", "P1 Pedal 1"), field(":WHEEL", "Paddle")
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local frame, done = 0, false
emu.register_frame_done(function()
  frame = frame + 1
  if done then return end
  if mem:read_u8(0x501139) == 0x11 then done = true; return end
  local now = nil
  for _, s in ipairs(steps) do if frame >= s[1] then now = s end end
  if now then accel:set_value(now[2]); wheel:set_value(now[3]) end
end)
