require("model2")

function Init()

	TestSurface = Video_CreateSurfaceFromFile("scripts\\scanlines_default.png");
	wide=true
	press=0

	horizontal = Video_CreateSurfaceFromFile("./bezels/hor.png");
	vertical = Video_CreateSurfaceFromFile("./bezels/ver.png");
end

function Frame()
		if Input_IsKeyPressed(0x3F)==1 and press==0 then wide=not wide press=1
		elseif Input_IsKeyPressed(0x3F)==0 and press==1 then press=0
		end
		
	if wide==true then
		Model2_SetWideScreen(1)
	else
		Model2_SetWideScreen(0)
	end
end

function PostDraw()
	if Options.scanlines.value==1 then
		Video_DrawSurface(TestSurface,0,0);
	end

	width, height = Video_GetScreenSize()
	local textureHeight = 50
	local borderThickness

	if Options.bezels.value==1 then
		local borderThickness=4
		local adjustmentValue = textureHeight+borderThickness
		Video_DrawSurface(horizontal,0, -adjustmentValue);
		Video_DrawSurface(horizontal,0,height - (adjustmentValue - textureHeight + borderThickness));
		Video_DrawSurface(vertical, -adjustmentValue,0);
		Video_DrawSurface(vertical,width - (adjustmentValue - textureHeight + borderThickness), 0);
	elseif Options.bezels.value==2 then
		local borderThickness=8
		local adjustmentValue = textureHeight
		Video_DrawSurface(horizontal,0, -adjustmentValue);
		Video_DrawSurface(horizontal,0,height - (adjustmentValue - textureHeight + (borderThickness*2)));
		Video_DrawSurface(vertical, -adjustmentValue,0);
		Video_DrawSurface(vertical,width - (adjustmentValue - textureHeight + (borderThickness*2)), 0);
	elseif Options.bezels.value==3 then
		local borderThickness=12
		local adjustmentValue = textureHeight-borderThickness
		Video_DrawSurface(horizontal,0, -adjustmentValue);
		Video_DrawSurface(horizontal,0,height - (adjustmentValue - textureHeight + (borderThickness*3)));
		Video_DrawSurface(vertical, -adjustmentValue,0);
		Video_DrawSurface(vertical,width - (adjustmentValue - textureHeight + (borderThickness*3)), 0);
	else
		return
	end
end

function health_1p_cheat_f(value)
        I960_WriteWord(RAMBASE+0x1E70,208); -- 1P full health
end

function health_2p_cheat_f(value)
        I960_WriteWord(RAMBASE+0x1E72,208); -- 2P full health
end

Options =
{
	health_1p_cheat={name="1P Infinite Health",values={"Off","On"},runfunc=health_1p_cheat_f},
	health_2p_cheat={name="2P Infinite Health",values={"Off","On"},runfunc=health_2p_cheat_f},
	scanlines={name="Scanlines (50%)",values={"Off","On"}},
	bezels={name="Bezels size",values={"Off","Thin","Normal","Big"}}
}
