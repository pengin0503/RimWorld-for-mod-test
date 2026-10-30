using System;

namespace RWMT.CContext
{
    // Constructor shape was read from the hash-verified game metadata, not guessed.
    public static class DialogConstructor
    {
        public static object Create(Type dialogType, Type billType, Type positionType, object bill, object position)
        {
            var constructor = dialogType.GetConstructor(new[] { billType, positionType });
            if (constructor == null) throw new MissingMethodException();
            return constructor.Invoke(new[] { bill, position });
        }
    }
}
