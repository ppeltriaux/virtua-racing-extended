-- Phase 21: dump the select screen's tile RAM (0x700000), character RAM (0x780000) and palette RAM (0x900000) into
-- VR_SELECT_DIR: at frame 600 (before the coin: the boot's blocks and palettes), 1, 2, 3 and 10 frames after every
-- change of the shown index [0x501942] (review: a copy caught mid-way would show for a frame), and at the frames listed in VR_SELECT_DUMP. Files: <frame>_<menu index>_{tile,char,pal}.bin.
-- Loaded by autoplay.lua when VR_SELECT_DIR is set.
local dir = os.getenv("VR_SELECT_DIR")
local fixed = {[600] = true}
for f in string.gmatch(os.getenv("VR_SELECT_DUMP") or "", "%d+") do fixed[tonumber(f)] = true end
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local frame, shown, due = 0, nil, {}
local function dump()
  local tag = string.format("%s/%d_%d", dir, frame, mem:read_u8(0x501940))
  for _, r in ipairs({{"tile", 0x700000, 0x70ffff}, {"char", 0x780000, 0x7fffff}, {"pal", 0x900000, 0x903fff}}) do
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
  if fixed[frame] or due[frame] then dump() end
end)
