-- Weather stage 3, fix round 1 (M5, tests/test_weather_cover.py): what the rain draws while the camera approaches a tunnel. At the end
-- of every frame whose cover mode (VR_RECS_MODE "<hex address>:<n>[,<n>...]", fix round 2: several modes) is one of the n, the display list the pass wrote (0x600000.. or
-- 0x610000.., from the game's write pointer 0x5017f4 to its start) is walked for the storm's object records (word 0 0xb, word 13 1,
-- the polygon word at +60 within VR_RECS_POLY "<hex lo>:<hex hi>": the rain's and the cover's objects) and each one's translation
-- (+40 +44 +48: the cluster's or splash's position in view space) and its kind (fix round 2: 0 a drop cluster, below VR_RECS_SPLASH,
-- the polygon word of the first splash object; 1 a splash, below VR_RECS_SINGLE, the first single drop; 2 a single drop) are logged
-- with the camera matrix 0x501b00 of that frame:
--   R <frame> <m0..m11> <n> <x y z k>...   (frames count from 1)
-- Loaded with VR_EXTRA_LUA. Env: VR_RECS_LOG (path), VR_RECS_MODE, VR_RECS_POLY. Frames count from 1 at the first frame end.
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local out = assert(io.open(assert(os.getenv("VR_RECS_LOG"), "rain_records.lua: VR_RECS_LOG is not set"), "w"))
local mode_at, modes = string.match(assert(os.getenv("VR_RECS_MODE")), "^(%x+):([%d,]+)$")
mode_at = tonumber(mode_at, 16)
local mode_is = {}
for v in string.gmatch(modes, "%d+") do mode_is[tonumber(v)] = true end
local lo, hi = string.match(assert(os.getenv("VR_RECS_POLY")), "^(%x+):(%x+)$")
lo, hi = tonumber(lo, 16), tonumber(hi, 16)
local splash, single = tonumber(assert(os.getenv("VR_RECS_SPLASH")), 16), tonumber(assert(os.getenv("VR_RECS_SINGLE")), 16)
local function f32(a) return (string.unpack("<f", string.pack("<I4", mem:read_u32(a)))) end
local frame, lines = 0, 0
emu.register_frame_done(function()
  frame = frame + 1
  if not mode_is[mem:read_u32(mode_at)] then return end
  local ptr = mem:read_u32(0x5017f4)
  local base = ptr & 0xff0000
  if base ~= 0x600000 and base ~= 0x610000 then return end
  local t = {}
  for k = 0, 11 do t[#t + 1] = string.format("%.5f", f32(0x501b00 + 4 * k)) end
  local recs, n = {}, 0
  for a = base, ptr - 68, 4 do
    if mem:read_u32(a) == 0xb and mem:read_u32(a + 52) == 1 then
      local p = mem:read_u32(a + 60)
      if p >= lo and p < hi then
        n = n + 1
        recs[#recs + 1] = string.format("%.3f %.3f %.3f %d", f32(a + 40), f32(a + 44), f32(a + 48), p < splash and 0 or p < single and 1 or 2)
      end
    end
  end
  out:write(string.format("R %d %s %d %s\n", frame, table.concat(t, " "), n, table.concat(recs, " ")))
  lines = lines + 1
  if lines % 50 == 0 then out:flush() end
end)
emu.add_machine_stop_notifier(function() out:write("END\n"); out:close() end)
