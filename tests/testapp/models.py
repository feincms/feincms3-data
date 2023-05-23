from django.db import models


class Tag(models.Model):
    name = models.CharField(default="name", max_length=20)
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True)

    def __str__(self):
        return self.name


class Parent(models.Model):
    name = models.CharField(default="name", max_length=20)
    tags = models.ManyToManyField(Tag, related_name="+")

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name


class Child(models.Model):
    name = models.CharField(default="name", max_length=20)

    class Meta:
        abstract = True
        ordering = ["id"]

    def __str__(self):
        return self.name


class Child1(Child):
    parent = models.ForeignKey(Parent, on_delete=models.CASCADE)


class Child2(Child):
    parent = models.ForeignKey(Parent, on_delete=models.PROTECT)


class Related(models.Model):
    name = models.CharField(default="name", max_length=20)
    related_to = models.ForeignKey(Parent, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return self.name


class UniqueSlug(models.Model):
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.slug


class UniqueSlugMTI(UniqueSlug):
    pass
