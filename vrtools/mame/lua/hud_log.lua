-- Phase 26 stage 3 (Task 6): the race HUD's level word / course name cells. Loaded by autoplay.lua when VR_HUD_LOG (path) is
-- set. Keyed on the mode byte 0x501138, never on absolute frames: one line at the frame end 60 frames after the first frame end
-- the mode reads 0x14 (the race), one at the first frame end it reads 0x1a (the goal), and one at the race load: the first frame
-- end in modes 0x11-0x13 at which row 45, column 58 (the level word's last cell) is not blank after a frame end with it blank
-- (0x8020) in those modes, so the label the HUD's first handler printed at the load, with the colour cell as that frame left it
-- (the HUD's per-frame code rewrites it from the next frame on):
--   H <frame> <mode> <attr> <row 44: 22 words> <row 45: 22 words>
-- attr is the byte [0x501434] (the colour cell of the level word's printer 0xff8926); the words are layer 0's tile words
-- (0x700000 + 0x80 a row + 2 a column) on rows 44 and 45, columns 40-61; hex but the frame. Frames are counted from 1 at the
-- first frame end, as autoplay.lua counts them.
local out = assert(io.open(os.getenv("VR_HUD_LOG"), "w"))
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local frame, race_at, race_done, goal_done, blank_seen, load_done = 0, nil, false, false, false, false
local function line(mode)
  local s = {string.format("H %d %02x %x", frame, mode, mem:read_u8(0x501434))}
  for _, row in ipairs({44, 45}) do
    for col = 40, 61 do s[#s + 1] = string.format("%x", mem:read_u16(0x700000 + 0x80 * row + 2 * col)) end
  end
  out:write(table.concat(s, " ") .. "\n"); out:flush()
end
emu.register_frame_done(function()
  frame = frame + 1
  local mode = mem:read_u8(0x501138)
  if mode >= 0x11 and mode <= 0x13 and not load_done then
    local last = mem:read_u16(0x700000 + 0x80 * 45 + 2 * 58)
    if last == 0x8020 then blank_seen = true
    elseif blank_seen then
      load_done = true
      line(mode)
    end
  end
  if mode == 0x14 and not race_at then race_at = frame end
  if race_at and not race_done and frame == race_at + 60 then
    race_done = true
    line(mode)
  end
  if mode == 0x1A and not goal_done then
    goal_done = true
    line(mode)
  end
end)
