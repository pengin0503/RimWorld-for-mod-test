using System;

namespace Prepatcher
{
    // Names and shapes as Prepatcher-based mods use them; no behaviour of their own.
    [AttributeUsage(AttributeTargets.Method)]
    public class PrepatcherFieldAttribute : Attribute
    {
    }

    [AttributeUsage(AttributeTargets.Method)]
    public class DefaultValueAttribute : Attribute
    {
        public DefaultValueAttribute(object defaultValue)
        {
            DefaultValue = defaultValue;
        }

        public object DefaultValue { get; }
    }
}
