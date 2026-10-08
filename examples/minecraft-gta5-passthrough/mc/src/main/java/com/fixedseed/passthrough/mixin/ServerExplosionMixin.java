package com.fixedseed.passthrough.mixin;

import com.fixedseed.passthrough.WorldBridge;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.ServerExplosion;
import net.minecraft.world.phys.Vec3;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** Every server explosion (TNT, creepers, beds, ...) is reported to the host so it can set off its own. */
@Mixin(ServerExplosion.class)
abstract class ServerExplosionMixin {
	@Shadow
	public abstract Vec3 center();

	@Shadow
	public abstract float radius();

	@Shadow
	public abstract Entity getDirectSourceEntity();

	@Inject(method = "explode", at = @At("HEAD"))
	private void passthrough$report(final CallbackInfoReturnable<Integer> cir) {
		Entity source = this.getDirectSourceEntity();
		WorldBridge.onExplosion(this.center(), this.radius(), source == null ? "" : BuiltInRegistries.ENTITY_TYPE.getKey(source.getType()).getPath());
	}
}
