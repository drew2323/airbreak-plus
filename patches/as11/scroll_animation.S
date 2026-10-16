.syntax unified
.thumb
.text
.balign 4
.global start
.type start, %function
.thumb_func
start:
    // Scale the clamped scroll step, then replay the reviewed native sequence.
    add.w r3, r3, r3, lsr #1 // x1.5
    //add.w r3, r3, r3         // x2
.global scroll_animation_displaced
.type scroll_animation_displaced, %object
scroll_animation_displaced:
    .rept 3
    nop
    .endr
.size scroll_animation_displaced, . - scroll_animation_displaced
.balign 4
    ldr.w pc, scroll_animation_resume
.size start, . - start

.global scroll_animation_resume
.type scroll_animation_resume, %object
scroll_animation_resume:
    .word 0
.size scroll_animation_resume, 4
