from django.db import models


class Tag(models.Model):
    name = models.CharField(default="name", max_length=20)
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True)


class Parent(models.Model):
    name = models.CharField(default="name", max_length=20)
    tags = models.ManyToManyField(Tag, related_name="+")

    class Meta:
        ordering = ["id"]


class Child(models.Model):
    name = models.CharField(default="name", max_length=20)

    class Meta:
        abstract = True
        ordering = ["id"]


class Child1(Child):
    parent = models.ForeignKey(Parent, on_delete=models.CASCADE)


class Child2(Child):
    parent = models.ForeignKey(Parent, on_delete=models.PROTECT)
