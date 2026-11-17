-- Phase 32: the race HUD's bottom rows (the course's name on rows 44-45, the word REVERSE under it on rows 46-47 in a reverse
-- race). Loaded by autoplay.lua when VR_HUDROWS_LOG (path) is set. Keyed on the mode byte 0x501138, never on absolute frames; a
-- session can hold several races (race_end.lua's VR_END_NEXT), numbered from 1 at each race load (the first frame end the mode
-- reads 0x11 after a frame end outside 0x11-0x14). Lines (hex but the frame and the race):
--   R <frame> <mode> <tag> <race> <rows 44, 45, 46, 47 of layer 0: 64 words each, columns 0-63>
--     tags: load   the frame end the name is printed (row 45, column 58 not blank after a frame end with it blank, modes 0x11-0x13)
--           race   60 frames after the first frame end in mode 0x14
--           lap    every 500 frames after that while the mode reads 0x14
--           goal   the first frame end in mode 0x1a
--           m      the first frame end of every other mode after the first race load (the results, the attract, the next select)
--           m30    30 frames later, the mode still the same
--   T <frame> <race> <writes>
--     with every lap line, and at the first frame end outside modes 0x14, 0x19 and 0x1a after a race line (a race's last T line
--     is its count): the writes so far, from that race line's frame end on, to rows 44-47 of layer 0 at columns 19-63 (the cells
--     the name and the word live in, clear of the SPEED figures on columns 2-11 and of the manual transmission's gear maps on
--     columns 14 and 17): a write tap, so a cell rewritten with the same word counts. A frame's writes count when its frame end
--     still reads one of those modes (the frame the mode leaves them in is the next scene's: mode 0x15 clears the layer in it)
--   X <frame> <race> <row> <column> <word>
--     each of a race's first 40 such writes (the word hex)
--   C <frame> <race>     VR_HUDROWS_COIN=n: Coin 1 pressed n frames after each race line, for 10 frames (a coin during a race)
-- Frames are counted from 1 at the first frame end, as autoplay.lua counts them.
local out = assert(io.open(os.getenv("VR_HUDROWS_LOG"), "w"))
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local frame, race, last_mode = 0, 0, -1
local race_at, race_done, goal_done, blank_seen, load_done, lap_at, mode_at = nil, false, false, false, false, nil, nil
local counting, writes, pending = false, 0, {}
local coin_after, coin_at = tonumber(os.getenv("VR_HUDROWS_COIN") or ""), nil
local coin
if coin_after then
  for name, f in pairs(manager.machine.ioport.ports[":IN.0"].fields) do if name == "Coin 1" then coin = f end end
  assert(coin, "no Coin 1 field")
end
local function line(mode, tag)
  local s = {string.format("R %d %02x %s %d", frame, mode, tag, race)}
  for row = 44, 47 do
    for col = 0, 63 do s[#s + 1] = string.format("%x", mem:read_u16(0x700000 + 0x80 * row + 2 * col)) end
  end
  out:write(table.concat(s, " ") .. "\n"); out:flush()
end
_G.vr_hudrows_tap = mem:install_write_tap(0x700000 + 0x80 * 44, 0x700000 + 0x80 * 48 - 1, "vr_hudrows", function(offset, data, mask)
  if not counting then return end
  local row, col = (offset - 0x700000) // 0x80, ((offset - 0x700000) % 0x80) // 2
  if col >= 19 then
    pending[#pending + 1] = {row, col, data}
  end
end)
emu.register_frame_done(function()
  frame = frame + 1
  local mode = mem:read_u8(0x501138)
  local racing = mode >= 0x11 and mode <= 0x14
  if mode == 0x11 and not (last_mode >= 0x11 and last_mode <= 0x14) then
    race = race + 1
    race_at, race_done, goal_done, blank_seen, load_done, lap_at = nil, false, false, false, false, nil
  end
  if counting and (mode == 0x14 or mode == 0x19 or mode == 0x1a) then     -- this frame's writes are the race's
    for _, w in ipairs(pending) do
      writes = writes + 1
      if writes <= 40 then out:write(string.format("X %d %d %d %d %x\n", frame, race, w[1], w[2], w[3])) end
    end
  end
  pending = {}
  if counting and not (mode == 0x14 or mode == 0x19 or mode == 0x1a) then
    counting = false
    out:write(string.format("T %d %d %d\n", frame, race, writes)); out:flush()
  end
  if race > 0 then
    if mode >= 0x11 and mode <= 0x13 and not load_done then
      local last = mem:read_u16(0x700000 + 0x80 * 45 + 2 * 58)
      if last == 0x8020 then blank_seen = true
      elseif blank_seen then load_done = true; line(mode, "load") end
    end
    if mode == 0x14 and not race_at then race_at = frame end
    if race_at and not race_done and frame == race_at + 60 then
      race_done = true; lap_at = frame + 500
      line(mode, "race")
      counting, writes = true, 0
      if coin_after then coin_at = frame + coin_after end
    end
    if lap_at and mode == 0x14 and frame == lap_at then lap_at = frame + 500; line(mode, "lap")
      out:write(string.format("T %d %d %d\n", frame, race, writes)); out:flush()
    end
    if mode == 0x1a and not goal_done then goal_done = true; line(mode, "goal") end
    if mode ~= last_mode and not racing and mode ~= 0x19 and mode ~= 0x1a then mode_at = frame; line(mode, "m") end
    if mode_at and frame == mode_at + 30 and not racing and mode ~= 0x19 and mode ~= 0x1a then line(mode, "m30") end
  end
  if coin_at and frame == coin_at then coin:set_value(1); out:write(string.format("C %d %d\n", frame, race)); out:flush() end
  if coin_at and frame == coin_at + 10 then coin:set_value(0); coin_at = nil end
  last_mode = mode
end)
