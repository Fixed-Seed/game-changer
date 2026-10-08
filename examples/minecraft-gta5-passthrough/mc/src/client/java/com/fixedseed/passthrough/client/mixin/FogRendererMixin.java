package com.fixedseed.passthrough.client.mixin;

import com.fixedseed.passthrough.Passthrough;
import net.minecraft.client.renderer.fog.FogData;
import net.minecraft.client.renderer.fog.FogRenderer;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * No distance fog while a host is attached (the host has its own), and a black fog colour: the level pass clears
 * to (fog colour, alpha 0), so this leaves empty pixels at (0, 0, 0, 0) and the world layer comes out premultiplied.
 */
@Mixin(FogRenderer.class)
abstract class FogRendererMixin {
	private static final float FAR_AWAY = 1.0E7F;

	@Inject(method = "updateBuffer", at = @At("HEAD"))
	private void passthrough$noFog(final FogData fog, final CallbackInfo ci) {
		if (Passthrough.active) {
			fog.environmentalStart = FAR_AWAY;
			fog.environmentalEnd = FAR_AWAY * 2.0F;
			fog.renderDistanceStart = FAR_AWAY;
			fog.renderDistanceEnd = FAR_AWAY * 2.0F;
			fog.skyEnd = FAR_AWAY * 2.0F;
			fog.cloudEnd = FAR_AWAY * 2.0F;
			fog.color.set(0.0F, 0.0F, 0.0F, 0.0F);
		}
	}
}
