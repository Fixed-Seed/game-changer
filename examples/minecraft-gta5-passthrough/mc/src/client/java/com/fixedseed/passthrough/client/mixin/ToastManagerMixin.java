package com.fixedseed.passthrough.client.mixin;

import net.minecraft.client.gui.components.toasts.Toast;
import net.minecraft.client.gui.components.toasts.ToastManager;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** No pop-ups (advancements, recipes, tutorials) over the host's picture. */
@Mixin(ToastManager.class)
abstract class ToastManagerMixin {
	@Inject(method = "addToast(Lnet/minecraft/client/gui/components/toasts/Toast;)V", at = @At("HEAD"), cancellable = true)
	private void passthrough$noToasts(final Toast toast, final CallbackInfo ci) {
		ci.cancel();
	}
}
