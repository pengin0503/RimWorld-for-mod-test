#version 450
layout(location = 0) in vec3 inPosition; // @vertex Position required
void main()
{
    gl_Position = vec4(inPosition.xy * 2.0 - 1.0, 0.5, 1.0);
}
