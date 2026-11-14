-- Phase 26 stage 3 (Task 7): which screens show the middle slot's character blocks. Since Task 5 the direction screen puts its
-- arrows and caption in the middle slot's blocks (characters 0x3480..0x35ff, palettes 0x69..0x6b), where the game left the
-- chosen course's picture. Loaded by autoplay.lua when VR_SLOT_LOG (path) is set (or as VR_EXTRA_LUA). Keyed on the mode byte
-- 0x501138 (the mode the dispatcher runs), never on absolute frames. VR_DIRECTION_RAM (hex, course.DIRECTION_RAM; required): the
-- flag's address, whose next byte is the screen's DIR_PHASE.
--
-- A layer's visible cells (MAME's segas24_tile_device::draw_common): layer n's 64 x 64 map at 0x700000 + 0x2000 n; its
-- horizontal scroll hscr at 0x70a000 + 2n, its vertical scroll vscr at 0x70a008 + 2n (bit 15: the layer is not drawn), the
-- control word ctrl at 0x70a008 + 2 (n & 2). Plain scrolling (hscr bit 15 clear, ctrl & 0x6000 = 0): the 496 x 384 screen shows
-- the pixels from x = (-hscr) & 0x1ff, y = vscr & 0x1ff, wrapping at 512, so the 62 x 48 cells (63 x 49 when not on the 8-px
-- grid) they cover. With a per-line scroll table (hscr bit 15) every column of the visible rows counts, and with ctrl's special
-- window modes every cell of the layer: never fewer cells than the screen can show. A cell names the middle slot when its
-- character (tile word & 0x3fff) is in 0x3480..0x35ff (its palette, word >> 7 & 0xff, is then 0x69..0x6b, or 0xe9..0xeb with
-- bit 14).
--
-- The locked screen's characters: the middle slot's 384 characters (character RAM 0x7e9000..0x7ebfff) as they are at the first
-- frame end of the direction lock (DIR_PHASE, VR_DIRECTION_RAM + 1 (0x502295), = 2 in mode 0x10): the arrows, the caption and what the course select's
-- middle picture left after them. A cell shows the locked screen's characters when it names one of them that is not blank (not
-- all colour 0) and whose 32 bytes are still those.
--
-- Every second frame end (a logic frame) the visible cells of the four layers are scanned. Lines:
--   R <frame>                                    the locked screen's characters taken
--   S <frame> <mode> <n0> <n1> <n2> <n3> <m0> <m1> <m2> <m3> <kept> <hit>
--       at every frame end where one of the fields but the hit changes: n_k the visible cells of layer k that name the middle
--       slot (-1: the layer is not drawn), m_k those of them that show the locked screen's characters (0 before they are
--       taken); kept the middle slot's characters that are still the locked screen's non-blank ones (-1 before they are
--       taken); hit "-" or the first cell of the n's, "<layer>:<row>:<col>:<tile word>" (hex word)
--   D <frame> <mode> <file>
--       a dump of tile RAM (0x700000..0x70ffff: the four maps and the scroll words) as <file> and of the middle slot's
--       characters as <file> with "tile" replaced by "mid", into VR_SLOT_DUMP, VR_SLOT_DUMP_AFTER frames (default "2,60,300")
--       after every frame end the mode changes, from the race load (the first mode 0x11) on; and a snapshot (MAME's
--       snap/vr/NNNN.png, in order) with each when VR_SLOT_SNAPS=1
-- Frames are counted from 1 at the first frame end, as autoplay.lua counts them.
local out = assert(io.open(os.getenv("VR_SLOT_LOG"), "w"))
local dir = os.getenv("VR_SLOT_DUMP")
local snaps = os.getenv("VR_SLOT_SNAPS") == "1"
local delays = {}
for d in string.gmatch(os.getenv("VR_SLOT_DUMP_AFTER") or "2,60,300", "%d+") do delays[#delays + 1] = tonumber(d) end
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local flag_at = tonumber(os.getenv("VR_DIRECTION_RAM") or "", 16)   -- the flag (course.DIRECTION_RAM); DIR_PHASE is the byte after it
if not flag_at then error("slot_log.lua: VR_DIRECTION_RAM is missing or not hex: " .. tostring(os.getenv("VR_DIRECTION_RAM"))) end
local PHASE = flag_at + 1
local LO, HI = 0x3480, 0x35ff
local MID, MID_END = 0x780000 + 32 * LO, 0x780000 + 32 * (HI + 1) - 1
local BLANK = string.rep("\0", 32)
local frame, last, prev_mode, loaded, due, ref = 0, "", nil, false, {}, nil

local function span(origin, pixels)            -- the cells (0..63) a window of `pixels` from pixel `origin` covers, wrapping at 512
  local cells, seen = {}, {}
  for p = origin, origin + pixels - 1, 1 do
    local c = (p & 0x1ff) >> 3
    if not seen[c] then seen[c] = true; cells[#cells + 1] = c end
  end
  return cells
end
local ALL = span(0, 512)

local function scan()
  local counts, shows, hit = {}, {}, "-"
  local cur = mem:read_range(MID, MID_END, 8)
  local same = {}                             -- per middle character (0-based), 1 when it still shows the locked screen's
  local kept = -1
  if ref then
    kept = 0
    for k = 0, HI - LO do
      local r = ref:sub(32 * k + 1, 32 * k + 32)
      if r ~= BLANK and cur:sub(32 * k + 1, 32 * k + 32) == r then same[k] = true; kept = kept + 1 end
    end
  end
  for n = 0, 3 do
    local hscr, vscr = mem:read_u16(0x70a000 + 2 * n), mem:read_u16(0x70a008 + 2 * n)
    local ctrl = mem:read_u16(0x70a008 + 2 * (n & 2))
    if vscr & 0x8000 ~= 0 then counts[n + 1], shows[n + 1] = -1, 0
    else
      local rows, cols
      if ctrl & 0x6000 ~= 0 then rows, cols = ALL, ALL
      else
        rows = span(vscr & 0x1ff, 384)
        cols = (hscr & 0x8000 ~= 0) and ALL or span((-hscr) & 0x1ff, 496)
      end
      local k, m, base = 0, 0, 0x700000 + 0x2000 * n
      for _, r in ipairs(rows) do
        for _, c in ipairs(cols) do
          local w = mem:read_u16(base + 0x80 * r + 2 * c)
          local ch = w & 0x3fff
          if ch >= LO and ch <= HI then
            k = k + 1
            if same[ch - LO] then m = m + 1 end
            if hit == "-" then hit = string.format("%d:%d:%d:%x", n, r, c, w) end
          end
        end
      end
      counts[n + 1], shows[n + 1] = k, m
    end
  end
  return counts, shows, kept, hit
end

emu.register_frame_done(function()
  frame = frame + 1
  local mode = mem:read_u8(0x501138)
  if mode == 0x11 then loaded = true end
  if not ref and mode == 0x10 and mem:read_u8(PHASE) == 2 then
    ref = mem:read_range(MID, MID_END, 8)
    out:write(string.format("R %d\n", frame))
  end
  if loaded and dir and prev_mode ~= nil and mode ~= prev_mode then
    for _, d in ipairs(delays) do due[frame + d] = true end
  end
  prev_mode = mode
  if due[frame] then
    due[frame] = nil
    local name = string.format("%d_%02x_tile.bin", frame, mode)
    local f = assert(io.open(dir .. "/" .. name, "wb")); f:write(mem:read_range(0x700000, 0x70ffff, 8)); f:close()
    f = assert(io.open(dir .. "/" .. name:gsub("tile", "mid"), "wb")); f:write(mem:read_range(MID, MID_END, 8)); f:close()
    if snaps then manager.machine.video:snapshot() end
    out:write(string.format("D %d %02x %s\n", frame, mode, name))
  end
  if frame % 2 == 0 then
    local c, m, kept, hit = scan()
    local s = string.format("%02x %d %d %d %d %d %d %d %d %d", mode, c[1], c[2], c[3], c[4], m[1], m[2], m[3], m[4], kept)
    if s ~= last then out:write(string.format("S %d %s %s\n", frame, s, hit)); last = s end
  end
  out:flush()
end)
