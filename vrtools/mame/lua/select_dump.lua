-- Phase 21: dump the select screen's tile RAM (0x700000), character RAM (0x780000) and palette RAM (0x900000) into
-- VR_SELECT_DIR: at frame 600 (before the coin: the boot's blocks and palettes), 1, 2, 3 and 10 frames after every
-- change of the shown index [0x501942] (review: a copy caught mid-way would show for a frame), and at the frames listed in VR_SELECT_DUMP. Files: <frame>_<menu index>_{tile,char,pal}.bin.
-- Phase 26 stage 3 (Task 4): also <frame>_<menu index>_work.bin, the eight bytes 0x501438..0x50143f: the two words the
-- countdown font's printer 0xff870d reads (its character base >> 7 and its attribute).
-- Phase 26 stage 3 (Task 5): VR_SELECT_DUMP_SELECT, a list of delays d: also d frames after every frame end at which the mode
-- byte 0x501139 becomes 0x10 (each select screen's start, a second game's too).
-- Loaded by autoplay.lua when VR_SELECT_DIR is set.
local dir = os.getenv("VR_SELECT_DIR")
local fixed = {[600] = true}
for f in string.gmatch(os.getenv("VR_SELECT_DUMP") or "", "%d+") do fixed[tonumber(f)] = true end
local after_select = {}
for f in string.gmatch(os.getenv("VR_SELECT_DUMP_SELECT") or "", "%d+") do after_select[#after_select + 1] = tonumber(f) end
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local frame, shown, due, mode = 0, nil, {}, nil
local function dump()
  local tag = string.format("%s/%d_%d", dir, frame, mem:read_u8(0x501940))
  for _, r in ipairs({{"tile", 0x700000, 0x70ffff}, {"char", 0x780000, 0x7fffff}, {"pal", 0x900000, 0x903fff}, {"work", 0x501438, 0x50143f}}) do
    local f = assert(io.open(tag .. "_" .. r[1] .. ".bin", "wb")); f:write(mem:read_range(r[2], r[3], 8)); f:close()
  end
end
emu.register_frame_done(function()
  frame = frame + 1
  local s = mem:read_u16(0x501942)
  if frame > 600 and s ~= shown then
    shown = s
    for _, d in ipairs({1, 2, 3, 10}) do due[frame + d] = true end
  end
  local m = mem:read_u8(0x501139)
  if m == 0x10 and mode ~= 0x10 then
    for _, d in ipairs(after_select) do due[frame + d] = true end
  end
  mode = m
  if fixed[frame] or due[frame] then dump() end
end)
